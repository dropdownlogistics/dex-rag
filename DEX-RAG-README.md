# DDL RAG Pipeline — Dex Jr. × Archive Integration
# Dropdown Logistics — Chaos → Structured → Automated

## What This Is

A local RAG (Retrieval-Augmented Generation) pipeline that gives
Dex Jr. searchable memory over the entire DDL archive (10,165 files,
1.3 billion characters, 26 months of production).

All local. All free. No cloud. No API costs.

## Stack

- **Embedding model**: nomic-embed-text (via Ollama, ~274 MB)
- **Vector database**: ChromaDB (local, SQLite-backed)
- **Generation model**: qwen2.5-coder:7b (via Ollama, already installed)
- **Language**: Python 3

## Quick Start

### 1. Setup (run once)

```powershell
python dex-setup.py
```

This checks Ollama, pulls nomic-embed-text, installs ChromaDB.

### 2. Ingest (Phase 1: .txt files only)

```powershell
# Auto-detect archive location
python dex-ingest.py

# Or specify path
python dex-ingest.py --path "C:\Users\dkitc\OneDrive\99_DexUniverseArchive"

# Reset and rebuild from scratch
python dex-ingest.py --reset
```

Estimated time: ~75 minutes for 7,359 .txt files.
The script deduplicates, chunks, embeds, and stores.

### 3. Query

```powershell
# Single query
python dex-query.py "when did I first describe star schema"

# More results
python dex-query.py "what did I write about Beth" --top 10

# With Dex Jr. synthesis (pipes results to qwen2.5-coder)
python dex-query.py "commission engine" --synthesize

# Interactive mode
python dex-query.py --interactive

# Database stats
python dex-query.py --stats
```

### Interactive Mode

```
dex> when did I first mention BlindSpot
  (returns 5 relevant chunks with source files)

dex> s: what product concepts have I described
  (s: prefix triggers Dex Jr. synthesis of results)

dex> quit
```

## File Structure

```
~/.dex-jr/
  chromadb/          # Persistent vector database
    chroma.sqlite3   # SQLite storage

Scripts (place in repo or scripts folder):
  dex-setup.py       # Setup and dependency check
  dex-ingest.py      # Archive ingestion pipeline
  dex-query.py       # Query interface
```

## Architecture

```
Archive (10,165 files)
  → SHA-256 dedup (removes exact copies)
  → Text extraction (encoding fallback: utf-8 → cp1252 → latin-1)
  → Chunking (~500 tokens with overlap)
  → Embedding (nomic-embed-text via Ollama)
  → ChromaDB (local persistent vector store)
  → Query (natural language → embedding → similarity search)
  → Optional: pipe to Dex Jr. for synthesis
```

## Phase Roadmap

- **Phase 1** (now): .txt files (7,359 files, 624.9 MB)
- **Phase 2**: .md, .html, .json, .py, .ps1, .jsx (549 files)
- **Phase 3**: .csv, .xlsx, .docx text extraction (387 files)
- **Phase 4**: Integration with Dex Jr. generation pipeline + SYS-019

## Updating

Re-run `dex-ingest.py` at any time. It skips already-ingested files
(matched by SHA-256 hash). Only new or modified files get processed.

To force full rebuild: `python dex-ingest.py --reset`
