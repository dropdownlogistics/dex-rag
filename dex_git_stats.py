"""
dex_git_stats.py -- Automated repo analytics across DDL git repos.

Read-only git commands. No API, no tokens, no pushes.
Pulls with --ff-only before collecting stats (safe for read-only repos).

Usage:
  python dex_git_stats.py              # full report, all repos
  python dex_git_stats.py --week       # last 7 days only
  python dex_git_stats.py --ingest     # generate + save report to DDL_Ingest
  dex stats                            # via CLI
  dex stats --week                     # last 7 days

Step 61 | Authority: CLAUDE.md Rule 12 (telemetry)
"""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta

import dex_core

# ── Git helpers ──────────────────────────────────────────────────────────────

def git_cmd(repo_path: str, args: list[str], timeout: int = 30) -> str:
    """Run a git command in repo_path, return stdout. Empty string on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def git_pull_ff(repo_path: str) -> str:
    """Pull with --ff-only. Returns status string."""
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            out = result.stdout.strip()
            if "Already up to date" in out:
                return "up-to-date"
            return "pulled"
        # Extract just the meaningful error line (skip "From..." and "hint:" noise)
        err_lines = [
            l.strip() for l in result.stderr.strip().splitlines()
            if l.strip() and not l.strip().startswith(("From ", "hint:", "   "))
        ]
        reason = err_lines[-1][:60] if err_lines else "ff-only failed"
        return f"skipped: {reason}"
    except subprocess.TimeoutExpired:
        return "skipped: timeout"
    except (FileNotFoundError, OSError) as e:
        return f"skipped: {e}"


# ── Stats collection ────────────────────────────────────────────────────────

def collect_repo_stats(name: str, repo_path: str, days: int = 7) -> dict:
    """Collect all stats for a single repo."""
    since = f"{days} days ago"

    stats = {
        "name": name,
        "path": repo_path,
        "exists": os.path.isdir(os.path.join(repo_path, ".git")),
    }

    if not stats["exists"]:
        return stats

    # Pull first (safe --ff-only)
    stats["pull_status"] = git_pull_ff(repo_path)

    # Commit counts
    stats["commits_total"] = int(git_cmd(repo_path, ["rev-list", "--count", "HEAD"]) or "0")
    stats["commits_period"] = int(
        git_cmd(repo_path, ["rev-list", "--count", f"--since={since}", "HEAD"]) or "0"
    )
    stats["commits_30d"] = int(
        git_cmd(repo_path, ["rev-list", "--count", "--since=30 days ago", "HEAD"]) or "0"
    )

    # Lines changed (period)
    numstat = git_cmd(repo_path, [
        "log", f"--since={since}", "--pretty=tformat:", "--numstat",
    ])
    added, removed = 0, 0
    for line in numstat.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            try:
                added += int(parts[0])
                removed += int(parts[1])
            except ValueError:
                pass  # binary files show "-"
    stats["lines_added"] = added
    stats["lines_removed"] = removed

    # Last commit date + relative
    last_date_str = git_cmd(repo_path, ["log", "-1", "--format=%ci"])
    stats["last_commit"] = last_date_str
    if last_date_str:
        try:
            # git format: "2026-04-17 02:30:00 -0500"
            last_dt = datetime.strptime(last_date_str[:19], "%Y-%m-%d %H:%M:%S")
            delta = datetime.now() - last_dt
            if delta.days > 0:
                stats["last_commit_rel"] = f"{delta.days}d ago"
            else:
                hours = delta.seconds // 3600
                stats["last_commit_rel"] = f"{hours}h ago" if hours > 0 else "<1h ago"
        except ValueError:
            stats["last_commit_rel"] = "unknown"
    else:
        stats["last_commit_rel"] = "never"

    # Most active files (30 days, top 5)
    name_only = git_cmd(repo_path, [
        "log", "--since=30 days ago", "--pretty=format:", "--name-only",
    ])
    file_counts = Counter(
        line.strip() for line in name_only.splitlines() if line.strip()
    )
    stats["top_files"] = file_counts.most_common(5)

    # Branch count
    branches = git_cmd(repo_path, ["branch"])
    stats["branch_count"] = len([b for b in branches.splitlines() if b.strip()])

    # Recent commit messages (period)
    log_lines = git_cmd(repo_path, [
        "log", f"--since={since}", "--oneline",
    ])
    stats["recent_commits"] = [
        line.strip() for line in log_lines.splitlines() if line.strip()
    ][:15]  # cap at 15

    return stats


# ── Report generation ────────────────────────────────────────────────────────

def format_report(all_stats: list[dict], days: int) -> str:
    """Generate the human-readable report."""
    now = datetime.now()
    week_start = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    lines = []

    lines.append("=" * 65)
    lines.append(f"DDL GIT STATS -- {'Week' if days == 7 else str(days) + ' days'} of {week_start}")
    lines.append(f"Generated: {now.strftime('%Y-%m-%dT%H:%M:%S')}")
    lines.append("=" * 65)

    # Summary
    active = [s for s in all_stats if s.get("commits_period", 0) > 0]
    total_commits = sum(s.get("commits_period", 0) for s in all_stats)
    total_added = sum(s.get("lines_added", 0) for s in all_stats)
    total_removed = sum(s.get("lines_removed", 0) for s in all_stats)

    lines.append("")
    lines.append("SUMMARY")
    lines.append(f"  Total repos:     {len(all_stats)}")
    lines.append(f"  Active ({days}d):    {len(active)}")
    lines.append(f"  Commits ({days}d):   {total_commits}")
    lines.append(f"  Lines added:     {total_added:,}")
    lines.append(f"  Lines removed:   {total_removed:,}")

    # Per repo
    lines.append("")
    lines.append(f"PER REPO (last {days} days)")
    sorted_stats = sorted(all_stats, key=lambda s: s.get("commits_period", 0), reverse=True)
    for s in sorted_stats:
        if not s.get("exists"):
            lines.append(f"  {s['name']:<20} NOT FOUND")
            continue
        c = s.get("commits_period", 0)
        rel = s.get("last_commit_rel", "?")
        if c > 0:
            a = s.get("lines_added", 0)
            r = s.get("lines_removed", 0)
            lines.append(f"  {s['name']:<20} {c:>3} commits  +{a:,}/-{r:,}  last: {rel}")
        else:
            lines.append(f"  {s['name']:<20}   0 commits               last: {rel}")

        pull = s.get("pull_status", "")
        if pull and pull not in ("up-to-date", "pulled"):
            lines.append(f"  {'':20}   pull: {pull[:60]}")

    # Top files (30 days, across all repos)
    lines.append("")
    lines.append("TOP FILES (30 days)")
    all_files = []
    for s in all_stats:
        if not s.get("exists"):
            continue
        for fname, count in s.get("top_files", []):
            all_files.append((f"{s['name']}/{fname}", count))
    all_files.sort(key=lambda x: x[1], reverse=True)
    for path, count in all_files[:10]:
        lines.append(f"  {path:<50} {count:>3} changes")

    if not all_files:
        lines.append("  (none)")

    # Recent commits
    lines.append("")
    lines.append(f"RECENT COMMITS ({days} days)")
    for s in sorted_stats:
        if not s.get("recent_commits"):
            continue
        lines.append(f"  {s['name']}:")
        for msg in s["recent_commits"][:8]:
            lines.append(f"    {msg}")
        if len(s["recent_commits"]) > 8:
            lines.append(f"    ... +{len(s['recent_commits']) - 8} more")

    # Velocity (all-time context)
    lines.append("")
    lines.append("ALL-TIME CONTEXT")
    for s in sorted_stats:
        if not s.get("exists"):
            continue
        lines.append(
            f"  {s['name']:<20} {s.get('commits_total', 0):>5} total commits"
            f"  {s.get('branch_count', 0):>3} branches"
            f"  {s.get('commits_30d', 0):>4} in 30d"
        )

    lines.append("")
    lines.append("=" * 65)
    return "\n".join(lines)


# ── JSON logging ─────────────────────────────────────────────────────────────

def log_stats(all_stats: list[dict], days: int):
    """Append summary to dex-git-stats-log.jsonl."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "period": f"{days}d",
        "total_commits": sum(s.get("commits_period", 0) for s in all_stats),
        "total_added": sum(s.get("lines_added", 0) for s in all_stats),
        "total_removed": sum(s.get("lines_removed", 0) for s in all_stats),
        "active_repos": sum(1 for s in all_stats if s.get("commits_period", 0) > 0),
        "repos": {},
    }
    for s in all_stats:
        if not s.get("exists"):
            continue
        entry["repos"][s["name"]] = {
            "commits": s.get("commits_period", 0),
            "added": s.get("lines_added", 0),
            "removed": s.get("lines_removed", 0),
        }
    try:
        with open(dex_core.GIT_STATS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"  [WARN] Log write failed: {e}")


# ── Ingest ───────────────────────────────────────────────────────────────────

def save_for_ingest(report: str) -> str:
    """Save report to DDL_Ingest for next sweep pickup."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"DDL_GitStats_{date_str}.txt"
    filepath = os.path.join(dex_core.INGEST_DIR, filename)

    if not os.path.isdir(dex_core.INGEST_DIR):
        print(f"  [ERROR] Ingest directory not found: {dex_core.INGEST_DIR}")
        return ""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)
    return filepath


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="DDL git stats across all repos")
    parser.add_argument("--week", action="store_true",
                        help="Last 7 days only (default: 30 days)")
    parser.add_argument("--days", type=int, default=None,
                        help="Custom period in days")
    parser.add_argument("--ingest", action="store_true",
                        help="Save report to DDL_Ingest for corpus pickup")
    args = parser.parse_args()

    days = 7 if args.week else (args.days or 30)

    repos = dex_core.GIT_REPOS
    print(f"\n  Collecting stats from {len(repos)} repos ({days}-day window)...\n")

    all_stats = []
    for name, path in repos.items():
        print(f"  {name}...", end=" ", flush=True)
        stats = collect_repo_stats(name, path, days)
        if not stats.get("exists"):
            print("NOT FOUND")
        else:
            c = stats.get("commits_period", 0)
            pull = stats.get("pull_status", "")
            pull_tag = f" (pull: {pull})" if pull not in ("up-to-date",) else ""
            print(f"{c} commits{pull_tag}")
        all_stats.append(stats)

    report = format_report(all_stats, days)
    print()
    print(report)

    # Log to JSONL
    log_stats(all_stats, days)

    # Ingest if requested
    if args.ingest:
        filepath = save_for_ingest(report)
        if filepath:
            print(f"\n  Saved for ingest: {filepath}")
        else:
            print("\n  [WARN] Ingest save failed")


if __name__ == "__main__":
    main()
