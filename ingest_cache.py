"""
ingest_cache.py — Per-collection file ingest cache for dex-ingest.py.

Step 48: Fixes the scoped+fast file-level skip bug (CR-DDL-INGEST-FAST-SCOPED-001).
Tracks which files have been ingested into which collection, with content hashes,
enabling true file-level deduplication that is content-aware, not ID-aware.

Cache location: C:\\Users\\dkitc\\.dex-jr\\ingest_cache\\
Storage: one JSON file per collection (e.g. dex_canon_v2.json).

Authority: CR-DDL-INGEST-FAST-SCOPED-001
"""

import os
import json
import hashlib
import time
from datetime import datetime, timezone
from typing import Optional, Dict


# Default cache directory (Step 54: from dex_core)
from dex_core import INGEST_CACHE_DIR as CACHE_DIR


def hash_file(filepath: str) -> Optional[str]:
    """Compute SHA-256 hex digest of file content. Returns None on read error."""
    h = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                h.update(block)
        return h.hexdigest()
    except Exception:
        return None


class IngestCache:
    """
    Per-collection file ingest cache.

    Each collection gets its own JSON file mapping absolute filepaths to
    ingest metadata (content hash, chunk count, timestamp, source type).

    File locking: uses a .lock sidecar with retry. The nightly sweep is
    the only expected writer, but defense-in-depth for concurrent runs.
    """

    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        self._data: Dict[str, Dict[str, dict]] = {}  # collection_name -> {filepath -> entry}

    def _cache_path(self, collection_name: str) -> str:
        return os.path.join(self.cache_dir, f"{collection_name}.json")

    def _lock_path(self, collection_name: str) -> str:
        return self._cache_path(collection_name) + ".lock"

    def _acquire_lock(self, collection_name: str, timeout: float = 30.0) -> bool:
        """Acquire a file-based lock. Returns True on success."""
        lock = self._lock_path(collection_name)
        os.makedirs(self.cache_dir, exist_ok=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return True
            except FileExistsError:
                time.sleep(0.2)
        return False

    def _release_lock(self, collection_name: str) -> None:
        lock = self._lock_path(collection_name)
        try:
            os.remove(lock)
        except FileNotFoundError:
            pass

    def load(self, collection_name: str) -> Dict[str, dict]:
        """
        Load cache for a collection from disk. Returns dict keyed by filepath.
        If no cache file exists, returns empty dict (first run).
        """
        if collection_name in self._data:
            return self._data[collection_name]

        path = self._cache_path(collection_name)
        if not os.path.exists(path):
            self._data[collection_name] = {}
            return self._data[collection_name]

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # data is a dict keyed by filepath
            self._data[collection_name] = data
        except (json.JSONDecodeError, IOError) as e:
            print(f"  WARN: cache load failed for {collection_name} ({e}), starting fresh")
            self._data[collection_name] = {}

        return self._data[collection_name]

    def lookup(self, filepath: str, collection_name: str) -> Optional[dict]:
        """
        Look up a filepath in the cache for a given collection.
        Returns the cache entry dict or None if not found.
        """
        cache = self.load(collection_name)
        # Normalize path for consistent lookups
        norm = os.path.normpath(os.path.abspath(filepath))
        return cache.get(norm)

    def update(
        self,
        filepath: str,
        collection_name: str,
        content_hash: str,
        chunk_count: int,
        source_type: str,
    ) -> None:
        """
        Write or update a cache entry for a file in a collection.
        Persists to disk immediately with file locking.
        """
        cache = self.load(collection_name)
        norm = os.path.normpath(os.path.abspath(filepath))

        cache[norm] = {
            "filepath": norm,
            "filename": os.path.basename(filepath),
            "content_hash": content_hash,
            "collection": collection_name,
            "chunk_count": chunk_count,
            "ingested_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_type": source_type,
        }

        self._data[collection_name] = cache
        self._flush(collection_name)

    def _flush(self, collection_name: str) -> None:
        """Write the in-memory cache for a collection to disk."""
        os.makedirs(self.cache_dir, exist_ok=True)
        path = self._cache_path(collection_name)

        if not self._acquire_lock(collection_name):
            print(f"  WARN: could not acquire cache lock for {collection_name}, skipping write")
            return

        try:
            # Write to temp file then rename for atomicity
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data.get(collection_name, {}), f, indent=2, ensure_ascii=False)
            # os.replace is atomic on Windows when source and dest are on the same volume
            os.replace(tmp, path)
        except Exception as e:
            print(f"  WARN: cache flush failed for {collection_name}: {e}")
        finally:
            self._release_lock(collection_name)

    def build_from_collection(self, collection, collection_name: str) -> int:
        """
        Lazy-build cache from existing collection metadata.

        Queries the collection for all unique source_file values and creates
        cache entries with content_hash=None (pre-cache files — hash unknown).

        Returns the number of entries created.
        """
        cache = self.load(collection_name)
        if cache:
            # Cache already has entries — don't overwrite with partial metadata
            return 0

        count = collection.count()
        if count == 0:
            return 0

        print(f"  Building ingest cache from {collection_name} metadata ({count} chunks)...")

        # Query all metadata in batches to get unique source files
        seen_files: Dict[str, int] = {}  # source_file -> chunk_count
        batch_size = 10_000
        offset = 0

        while offset < count:
            try:
                result = collection.get(
                    include=["metadatas"],
                    limit=batch_size,
                    offset=offset,
                )
            except Exception as e:
                print(f"  WARN: cache build query failed at offset {offset}: {e}")
                break

            metadatas = result.get("metadatas", [])
            if not metadatas:
                break

            for md in metadatas:
                if not md:
                    continue
                # Try source_file first (STD-DDL-METADATA-001), then filename (legacy)
                source = md.get("source_file") or md.get("filename") or ""
                if source:
                    seen_files[source] = seen_files.get(source, 0) + 1

            offset += len(metadatas)

        # Create cache entries with null hash (pre-cache)
        entries_created = 0
        for source_file, chunk_count in seen_files.items():
            # We don't have the absolute path — store the filename as key
            # These entries will force re-evaluation on next encounter
            cache[source_file] = {
                "filepath": source_file,
                "filename": os.path.basename(source_file),
                "content_hash": None,  # unknown — ingested pre-cache
                "collection": collection_name,
                "chunk_count": chunk_count,
                "ingested_at": None,  # unknown
                "source_type": "unknown",
            }
            entries_created += 1

        self._data[collection_name] = cache
        self._flush(collection_name)
        print(f"  Cache built: {entries_created} source files from {collection_name}")
        return entries_created

    def decide(self, filepath: str, content_hash: str, collection_name: str) -> str:
        """
        5-step decision logic for whether to ingest a file.

        Returns one of:
          - "NEW"                    — cache miss, first ingest
          - "SKIPPED (unchanged)"    — cache hit, hash matches
          - "RE-CHUNKED (modified)"  — cache hit, hash differs
          - "SKIPPED (no cache, upsert expected)" — pre-cache entry (null hash)

        For "SKIPPED (no cache, upsert expected)": the file was ingested
        before the cache existed. We don't know its hash, so we can't
        skip confidently. But we record the current hash for next time.
        This is a transitional state that self-heals on first encounter.
        """
        entry = self.lookup(filepath, collection_name)

        # Also check by filename (for lazy-built cache entries keyed by filename)
        if entry is None:
            cache = self.load(collection_name)
            basename = os.path.basename(filepath)
            entry = cache.get(basename)

        if entry is None:
            # Cache miss — genuinely new file
            return "NEW"

        cached_hash = entry.get("content_hash")

        if cached_hash is None:
            # Pre-cache entry — hash unknown. File was ingested before
            # cache existed. Can't skip (content may differ from what's
            # in the collection). Treat as "needs re-evaluation".
            # The caller should ingest and then update the cache with
            # the current hash so future runs can skip properly.
            return "SKIPPED (no cache, upsert expected)"

        if cached_hash == content_hash:
            # Hash match — file content hasn't changed since last ingest
            return "SKIPPED (unchanged)"

        # Hash mismatch — file was modified since last ingest
        return "RE-CHUNKED (modified)"
