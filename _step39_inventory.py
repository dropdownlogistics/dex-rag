"""Step 39A — gloss-candidate inventory. Read-only. Counts chunks
per term across _v2 collections and checks for definition files."""
from __future__ import annotations
import json
import sys

import chromadb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"

CANON_TERMS = [
    "CottageHumble", "AccidentalInsight", "AccidentalIntelligence",
    "SideDoor", "AcceptableArrogance", "ExpertiseInvisibility",
    "CoherentVelocity", "GuidedEmergence", "OccamsOpposite",
    "ModelCourtesy", "GroundTune", "HYFS", "MetaMeta", "AppeaseMent",
    "WanderingDirection", "CathedralPlanned", "SessionAsExemplar",
    "Charlie Conway", "MDN", "BringYourData", "TrustANDVerify",
    "AccidentalEntity", "PortableRecord", "Graph Holds", "AuditorsEye",
    "AutoCouncil",
]
F_CODES = [f"F{n}" for n in range(1, 7)]
OBS_SAMPLES = ["OBS-DJ-001", "OBS-DJ-004", "OBS-AF-001"]
ENTITIES = [
    "Beth Epperson", "Clayton Hotze", "Cara Borkowski",
    "Jennifer Parker", "Dave Kitchens",
    # shorter variants worth checking
    "Bryce", "Connor", "Emily", "GK",
]


def has_definition_file(term: str, all_sources: set) -> tuple[bool, list[str]]:
    """Return (True, matches) if a file appears to define the term."""
    term_norm = term.replace(" ", "")
    term_lower = term.lower()
    candidates = []
    for sf in all_sources:
        if not sf:
            continue
        sf_lower = sf.lower()
        stem = sf_lower.rsplit(".", 1)[0]
        # exact filename match
        if stem.endswith(term_norm.lower()) and ("/" not in stem and "\\" not in stem[:-len(term_norm)]):
            candidates.append(sf)
            continue
        # governance prefixes naming the term
        for pfx in ("std-ddl-", "cr-", "pro-ddl-", "gloss-ddl-", "profile-ddl-"):
            if pfx in sf_lower and term_lower.replace(" ", "") in sf_lower.replace(" ", "").replace("-", ""):
                if sf not in candidates:
                    candidates.append(sf)
                break
    return (len(candidates) > 0, candidates[:3])


def main():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    canon = client.get_collection("dex_canon_v2")
    archive = client.get_collection("ddl_archive_v2")

    # Build set of all source_files across both collections (paged)
    print("Collecting source_files from both collections...")
    all_sources: set[str] = set()
    for col in (canon, archive):
        offset = 0
        PAGE = 2000
        while True:
            try:
                page = col.get(limit=PAGE, offset=offset, include=["metadatas"])
            except Exception as e:
                print(f"  [warn] page {offset} failed: {e}")
                break
            metas = page.get("metadatas") or []
            if not metas:
                break
            for m in metas:
                sf = (m or {}).get("source_file") or ""
                if sf:
                    all_sources.add(sf)
            if len(metas) < PAGE:
                break
            offset += PAGE
    print(f"  total unique source_files: {len(all_sources)}")

    all_items: list[dict] = []
    groups = [("canon", CANON_TERMS), ("entity", ENTITIES),
              ("fcode", F_CODES), ("obs", OBS_SAMPLES)]
    for typ, terms in groups:
        for t in terms:
            try:
                cn = canon.get(where_document={"$contains": t}, include=[])
                an = archive.get(where_document={"$contains": t}, include=[])
            except Exception as e:
                print(f"  [warn] {t}: {e}")
                continue
            has_def, matches = has_definition_file(t, all_sources)
            # Recommend artifact
            if typ == "entity":
                rec = "PROFILE" if not has_def else "NONE"
            elif typ == "fcode":
                rec = "GLOSS" if not has_def else "NONE"
            elif typ == "obs":
                rec = "STD" if not has_def else "NONE"
            else:
                rec = "GLOSS" if not has_def else "NONE"
            all_items.append({
                "term": t,
                "type": typ,
                "canon": len(cn.get("ids", []) or []),
                "archive": len(an.get("ids", []) or []),
                "total": len(cn.get("ids", []) or []) + len(an.get("ids", []) or []),
                "has_def": has_def,
                "def_matches": matches,
                "recommend": rec,
            })

    # Sort by total desc
    all_items.sort(key=lambda x: -x["total"])

    print("\nINVENTORY (sorted by total chunk density)")
    print(f"{'term':<28} {'type':<8} {'canon':>7} {'arch':>7} {'total':>8}  def? recommend  matches")
    print("-" * 110)
    for it in all_items:
        dmark = "YES" if it["has_def"] else "no"
        m = "; ".join([s[:40] for s in it["def_matches"][:2]]) if it["def_matches"] else ""
        print(f"{it['term']:<28} {it['type']:<8} {it['canon']:>7} {it['archive']:>7} {it['total']:>8}  {dmark:>4}  {it['recommend']:<8}  {m}")

    with open("_step39_inventory.json", "w", encoding="utf-8") as f:
        json.dump(all_items, f, indent=2)


if __name__ == "__main__":
    main()
