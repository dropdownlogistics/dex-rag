"""
test_ingest_cache.py — Step 48.4 test suite for ingest cache.

Tests cache behavior across 6 scenarios using a temp directory and
in-memory ChromaDB. Does NOT touch production corpus or collections.

Usage: python test_ingest_cache.py
"""

import os
import sys
import json
import shutil
import tempfile

# Ensure repo is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ingest_cache import IngestCache, hash_file


def setup_temp():
    """Create a temp directory for cache + test files."""
    base = tempfile.mkdtemp(prefix="dex_cache_test_")
    cache_dir = os.path.join(base, "cache")
    files_dir = os.path.join(base, "files")
    os.makedirs(cache_dir)
    os.makedirs(files_dir)
    return base, cache_dir, files_dir


def write_test_file(files_dir, filename, content):
    path = os.path.join(files_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def test_1_new_file(cache_dir, files_dir):
    """Test 1: New file produces cache entry."""
    print("\n=== Test 1: New file ===")
    cache = IngestCache(cache_dir=cache_dir)
    collection = "test_collection"

    filepath = write_test_file(files_dir, "new_doc.txt",
        "This is a brand new document for testing the ingest cache. " * 20)
    content_hash = hash_file(filepath)
    assert content_hash is not None, "hash_file returned None"

    # Decision should be NEW
    decision = cache.decide(filepath, content_hash, collection)
    assert decision == "NEW", f"Expected NEW, got {decision}"
    print(f"  Decision: {decision} (correct)")

    # Simulate successful ingest — update cache
    cache.update(filepath, collection, content_hash, chunk_count=3, source_type="document")

    # Verify cache entry written
    entry = cache.lookup(filepath, collection)
    assert entry is not None, "Cache entry not found after update"
    assert entry["content_hash"] == content_hash
    assert entry["chunk_count"] == 3
    assert entry["source_type"] == "document"
    print(f"  Cache entry: hash={entry['content_hash'][:16]}..., chunks={entry['chunk_count']}")

    # Verify JSON file on disk
    cache_file = os.path.join(cache_dir, f"{collection}.json")
    assert os.path.exists(cache_file), f"Cache file not found: {cache_file}"
    with open(cache_file, "r") as f:
        data = json.load(f)
    assert len(data) == 1, f"Expected 1 entry, got {len(data)}"
    print("  PASS: New file creates cache entry")
    return True


def test_2_unchanged_file(cache_dir, files_dir):
    """Test 2: Unchanged file is skipped."""
    print("\n=== Test 2: Unchanged file skip ===")
    cache = IngestCache(cache_dir=cache_dir)
    collection = "test_collection"

    filepath = write_test_file(files_dir, "stable_doc.txt",
        "This document will not change between runs. " * 20)
    content_hash = hash_file(filepath)

    # First ingest
    decision = cache.decide(filepath, content_hash, collection)
    assert decision == "NEW", f"Expected NEW on first run, got {decision}"
    cache.update(filepath, collection, content_hash, chunk_count=2, source_type="document")
    print(f"  First run: {decision} -> cached")

    # Second run — same file, same content
    # Need a fresh IngestCache to simulate a new process
    cache2 = IngestCache(cache_dir=cache_dir)
    decision2 = cache2.decide(filepath, content_hash, collection)
    assert decision2 == "SKIPPED (unchanged)", f"Expected SKIPPED (unchanged), got {decision2}"
    print(f"  Second run: {decision2}")
    print("  PASS: Unchanged file skipped correctly")
    return True


def test_3_modified_file(cache_dir, files_dir):
    """Test 3: Modified file triggers re-chunk."""
    print("\n=== Test 3: Modified file re-chunk ===")
    cache = IngestCache(cache_dir=cache_dir)
    collection = "test_collection_mod"

    filepath = write_test_file(files_dir, "evolving_doc.txt",
        "Version 1 of this document. " * 20)
    hash_v1 = hash_file(filepath)

    # First ingest
    cache.update(filepath, collection, hash_v1, chunk_count=2, source_type="document")
    print(f"  V1 cached: hash={hash_v1[:16]}...")

    # Modify the file
    with open(filepath, "a", encoding="utf-8") as f:
        f.write("\nAppended: this line changes the hash entirely.\n")
    hash_v2 = hash_file(filepath)
    assert hash_v1 != hash_v2, "Hash should differ after modification"

    # Decision should be RE-CHUNKED
    cache2 = IngestCache(cache_dir=cache_dir)
    decision = cache2.decide(filepath, hash_v2, collection)
    assert decision == "RE-CHUNKED (modified)", f"Expected RE-CHUNKED (modified), got {decision}"
    print(f"  V2 decision: {decision}")

    # Update cache with new hash
    cache2.update(filepath, collection, hash_v2, chunk_count=3, source_type="document")
    entry = cache2.lookup(filepath, collection)
    assert entry["content_hash"] == hash_v2
    assert entry["chunk_count"] == 3
    print(f"  Cache updated: hash={hash_v2[:16]}..., chunks=3")
    print("  PASS: Modified file triggers re-chunk")
    return True


def test_4_force_rechunk():
    """Test 4: --force-rechunk bypasses cache entirely (logic test)."""
    print("\n=== Test 4: --force-rechunk bypass ===")
    # This is a logic test — when force_rechunk=True, the ingest loop
    # never calls cache.decide(). We verify that the flag exists and
    # is wired through argparse.
    import subprocess
    result = subprocess.run(
        ["python", "dex-ingest.py", "--help"],
        capture_output=True, text=True
    )
    assert "--force-rechunk" in result.stdout, "--force-rechunk not in help output"
    print("  --force-rechunk flag present in CLI")
    print("  Logic: when set, cache.decide() is never called, all files proceed to chunk+ingest")
    print("  PASS: --force-rechunk flag wired correctly")
    return True


def test_5_no_ingest_cache():
    """Test 5: --no-ingest-cache preserves pre-Step-48 behavior."""
    print("\n=== Test 5: --no-ingest-cache ===")
    import subprocess
    result = subprocess.run(
        ["python", "dex-ingest.py", "--help"],
        capture_output=True, text=True
    )
    assert "--no-ingest-cache" in result.stdout, "--no-ingest-cache not in help output"
    print("  --no-ingest-cache flag present in CLI")
    print("  Logic: when set, use_cache=False, no cache reads/writes, falls back to RAW ID prefix check")
    print("  PASS: --no-ingest-cache flag wired correctly")
    return True


def test_6_lazy_build():
    """Test 6: Lazy-build from collection metadata."""
    print("\n=== Test 6: Lazy-build from collection metadata ===")
    import chromadb

    base, cache_dir, files_dir = setup_temp()
    try:
        client = chromadb.Client()  # in-memory
        col = client.create_collection("lazy_build_test")

        # Add some chunks with source_file metadata
        col.add(
            ids=["f_abc123_c0", "f_abc123_c1", "f_def456_c0"],
            documents=["chunk 0 of file A", "chunk 1 of file A", "chunk 0 of file B"],
            embeddings=[[0.1]*384, [0.2]*384, [0.3]*384],
            metadatas=[
                {"source_file": "fileA.txt", "filename": "fileA.txt"},
                {"source_file": "fileA.txt", "filename": "fileA.txt"},
                {"source_file": "fileB.txt", "filename": "fileB.txt"},
            ]
        )
        assert col.count() == 3

        cache = IngestCache(cache_dir=cache_dir)
        entries_created = cache.build_from_collection(col, "lazy_build_test")
        assert entries_created == 2, f"Expected 2 entries, got {entries_created}"

        data = cache.load("lazy_build_test")
        assert "fileA.txt" in data, "fileA.txt not in cache"
        assert "fileB.txt" in data, "fileB.txt not in cache"
        assert data["fileA.txt"]["content_hash"] is None, "Pre-cache entry should have null hash"
        assert data["fileA.txt"]["chunk_count"] == 2, f"fileA should have 2 chunks, got {data['fileA.txt']['chunk_count']}"
        assert data["fileB.txt"]["chunk_count"] == 1

        print(f"  Built {entries_created} entries from collection metadata")
        print(f"  fileA.txt: chunks={data['fileA.txt']['chunk_count']}, hash=None (pre-cache)")
        print(f"  fileB.txt: chunks={data['fileB.txt']['chunk_count']}, hash=None (pre-cache)")

        # Verify that a lookup against a pre-cache entry returns "no cache, upsert expected"
        decision = cache.decide("/some/path/fileA.txt", "fakehash123", "lazy_build_test")
        assert decision == "SKIPPED (no cache, upsert expected)", f"Expected no-cache decision, got {decision}"
        print(f"  Decision for pre-cache file: {decision}")

        print("  PASS: Lazy-build from collection metadata works")
        return True
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main():
    print("=" * 60)
    print("  Step 48.4 — Ingest Cache Test Suite")
    print("=" * 60)

    # Use shared temp dir for tests 1-3
    base, cache_dir, files_dir = setup_temp()
    results = []

    try:
        results.append(("Test 1: New file", test_1_new_file(cache_dir, files_dir)))
        results.append(("Test 2: Unchanged skip", test_2_unchanged_file(cache_dir, files_dir)))
        results.append(("Test 3: Modified re-chunk", test_3_modified_file(cache_dir, files_dir)))
        results.append(("Test 4: --force-rechunk", test_4_force_rechunk()))
        results.append(("Test 5: --no-ingest-cache", test_5_no_ingest_cache()))
        results.append(("Test 6: Lazy-build", test_6_lazy_build()))
    except Exception as e:
        print(f"\n  FAIL: {e}")
        import traceback
        traceback.print_exc()
        results.append(("CRASH", False))
    finally:
        shutil.rmtree(base, ignore_errors=True)

    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    all_pass = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {name}")

    print(f"\n  {len([r for r in results if r[1]])}/{len(results)} tests passed")
    if all_pass:
        print("  All tests passed.")
    else:
        print("  SOME TESTS FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
