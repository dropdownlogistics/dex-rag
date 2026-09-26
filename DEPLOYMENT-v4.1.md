# v4.1 DEPLOYMENT CHECKLIST
# All changes, in order, with exact file paths

## STEP 1: Deploy Modelfile v4.1
```powershell
# Copy Modelfile to rig
# (save Modelfile.dexjr-v4.1 to C:\Users\dexjr\dex-rag\)

# Build the new model
cd C:\Users\dexjr\dex-rag
ollama create dexjr -f Modelfile.dexjr-v4.1

# Verify
ollama list | Select-String dexjr
```

## STEP 2: Fix bridge num_ctx override
```
File: C:\Users\dexjr\dex-rag\dex-bridge.py
Function: generate()
Change: "num_ctx": 16384  →  "num_ctx": 8192
```
One line. The bridge was forcing 16K context on every query,
overriding whatever the Modelfile set. This is likely the
root cause of Test 2's timeout — not the Modelfile's num_ctx.

## STEP 3: Update council GOVERNANCE block
```
File: C:\Users\dexjr\dex-rag\dex-council.py
Block: GOVERNANCE = """..."""
Replace: entire GOVERNANCE string with v4.1-aligned version
```
See council-governance-v4.1.py for the replacement text.

What was removed (v4.1 Modelfile now owns these):
- CottageHumble design tokens
- Operator behavioral patterns
- Canon > Archive weighting
- "When you don't know" fallback
- "Models advise, operator decides"

What stays (council-specific):
- Governance hierarchy (7 levels)
- Council structure + review mechanics
- Artifact type definitions
- Clinical boundary
- DDL/DexOS/MindFrame definitions (cloud models need these)

Estimated reduction: ~800 tokens → ~400 tokens.

## STEP 4: Ingest Modelfile v4.1 into canon
```powershell
# Save as .txt (ingest only scans .txt)
Copy-Item "C:\Users\dexjr\dex-rag\Modelfile.dexjr-v4.1" `
          "C:\Users\dexjr\99_DexUniverseArchive\00_Archive\DDL-Standards-Canon\Modelfile-dexjr-v4.1.txt"

# Run canon ingest
python dex-ingest.py "C:\Users\dexjr\99_DexUniverseArchive\00_Archive\DDL-Standards-Canon\Modelfile-dexjr-v4.1.txt" --canon
```
Note: Verify the exact ingest command syntax. The above assumes
BUILD CANON mode flag is --canon. Check dex-ingest.py --help.

## STEP 5: Test — re-run all three evidence prompts
```powershell
# Test 1: PM template default (should produce line-item verdicts)
python dex-bridge.py "CR-CORPUS-ARCH-001: [paste original prompt]"

# Test 2: Timeout (should complete within 120s at 8192 ctx)
python dex-bridge.py "CR-CONTENT-SOURCES-001: [paste original prompt]"

# Test 3: Hard refusal (should produce document analysis)
python dex-bridge.py "CR-MEMOREASE-001: [paste original prompt]"
```

## STEP 6: Verify no duplication
After deployment, run a bridge query and a council query.
Check that:
- Bridge output follows v4.1 response rules (no PM templates)
- Council output uses LOCK/REVISE/REJECT format
- No contradictory framing between Modelfile and injection
- CottageHumble tokens work (ask Dex Jr. to suggest colors for a component)

## ROLLBACK
```powershell
# Modelfile
ollama create dexjr -f Modelfile.dexjr-v3

# Bridge
# Revert num_ctx to 16384 (or keep 8192 if timeout was the issue)

# Council
# Revert GOVERNANCE to v3 block
```

## FILES MODIFIED
| File | Change | Risk |
|------|--------|------|
| Modelfile.dexjr-v4.1 | NEW — replaces v3 | Low (v3 preserved) |
| dex-bridge.py | num_ctx 16384→8192 | Low (one line) |
| dex-council.py | GOVERNANCE block | Medium (affects all council runs) |
| DDL-Standards-Canon/ | New .txt for ingestion | None |
