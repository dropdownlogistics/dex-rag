# dex.ps1 — Dex Jr. CLI router (mobile-first)
# Usage: dex <command> [args]
#
# Step 54.2 | Dropdown Logistics

param(
    [Parameter(Position=0)]
    [string]$Command,
    [Parameter(Position=1, ValueFromRemainingArguments)]
    [string[]]$Rest
)

$script_dir = Split-Path -Parent $MyInvocation.MyCommand.Path

switch ($Command) {
    { $_ -in "q", "query" }   { python "$script_dir\dex_jr_query.py" @Rest }
    { $_ -in "b", "bridge" }  { python "$script_dir\dex-bridge.py" @Rest }
    { $_ -in "c", "council" } { python "$script_dir\dex-council.py" @Rest }
    { $_ -in "r", "review" }  { python "$script_dir\dex_review.py" @Rest }
    { $_ -in "f", "fetch" }   { python "$script_dir\dex_fetch_external.py" @Rest }
    "health"                   { python "$script_dir\dex_health.py" @Rest }
    "status"                   { python "$script_dir\dex_health.py" --quick @Rest }
    "sweep"                    { python "$script_dir\dex-sweep.py" @Rest }
    "backup"                   { python "$script_dir\dex-backup.py" @Rest }
    "ingest"                   { python "$script_dir\dex-ingest.py" --path @Rest }
    "hosts"                    { python "$script_dir\dex-council.py" --host-status @Rest }
    "weights"                  { python "$script_dir\dex_weights.py" --stats @Rest }
    "stats"                    { python "$script_dir\dex_git_stats.py" @Rest }
    "api"                      { python "$script_dir\dex-search-api.py" @Rest }
    "repo-backup"              { python "$script_dir\dex_repo_backup.py" @Rest }
    "log" {
        Get-Content "$script_dir\dex-council-log.jsonl" -Encoding UTF8 |
            Select-Object -Last 5 |
            ForEach-Object {
                $d = $_ | ConvertFrom-Json
                $p = $d.prompt
                if ($p.Length -gt 60) { $p = $p.Substring(0, 60) + "..." }
                "$($d.timestamp.Substring(0,16)) | v$($d.version) | $($d.successful)/$($d.model_count) ok | $p"
            }
    }
    "pause" {
        if ($Rest -contains "--seat0") {
            Write-Host ""
            Write-Host "  SEAT 0 FAILSAFE — Pausing all automated tasks"
            Write-Host ""
            $tasks = @("DexSweep", "DexHealthCheck", "DexWeeklyEval",
                       "DexExternalFetch", "DexGitStats", "DexRepoBackup")
            foreach ($t in $tasks) {
                try {
                    Disable-ScheduledTask -TaskName $t -ErrorAction Stop
                    Write-Host "  [PAUSED] $t"
                } catch {
                    Write-Host "  [SKIP]   $t (not found)"
                }
            }
            Write-Host ""
            Write-Host "  All automated tasks paused."
            Write-Host "  To resume: dex resume"
            Write-Host ""

            $entry = @{
                timestamp = (Get-Date -Format o)
                action = "pause"
                triggered_by = "seat0"
            } | ConvertTo-Json -Compress
            Add-Content "$script_dir\dex-pause-log.jsonl" $entry
        } else {
            Write-Host "  Usage: dex pause --seat0"
            Write-Host "  This pauses ALL automated tasks."
            Write-Host "  Only use in emergencies or by Emily's request."
        }
    }
    "resume" {
        Write-Host ""
        Write-Host "  Resuming all automated tasks"
        Write-Host ""
        $tasks = @("DexSweep", "DexHealthCheck", "DexWeeklyEval",
                   "DexExternalFetch", "DexGitStats", "DexRepoBackup")
        foreach ($t in $tasks) {
            try {
                Enable-ScheduledTask -TaskName $t -ErrorAction Stop
                Write-Host "  [RESUMED] $t"
            } catch {
                Write-Host "  [SKIP]    $t (not found)"
            }
        }
        Write-Host ""
        Write-Host "  All automated tasks resumed."
        Write-Host ""

        $entry = @{
            timestamp = (Get-Date -Format o)
            action = "resume"
            triggered_by = "operator"
        } | ConvertTo-Json -Compress
        Add-Content "$script_dir\dex-pause-log.jsonl" $entry
    }
    default {
        Write-Host ""
        Write-Host "  dex <command> [args]"
        Write-Host ""
        Write-Host "  q, query    Query the corpus"
        Write-Host "  b, bridge   RAG bridge (query + generate)"
        Write-Host "  r, review   Council review parser + vote stats"
        Write-Host "  c, council  Run AutoCouncil"
        Write-Host "  f, fetch    Fetch external content from CSV"
        Write-Host "  health      Full health check (--quick for fast)"
        Write-Host "  status      Quick corpus status"
        Write-Host "  hosts       Host connectivity check"
        Write-Host "  sweep       Run nightly sweep"
        Write-Host "  backup      Run backup"
        Write-Host "  ingest      Ingest files from path"
        Write-Host "  weights     Show weight table"
        Write-Host "  stats       Git stats across all repos"
        Write-Host "  api         Start search API server"
        Write-Host "  repo-backup Mirror backup of all DDL repos"
        Write-Host "  pause       Pause all automated tasks (--seat0)"
        Write-Host "  resume      Resume all automated tasks"
        Write-Host "  log         Last 5 council runs"
        Write-Host ""
    }
}
