import chromadb
import os

ARCHIVE_PATH = r'C:\Users\dexjr\99_DexUniverseArchive'
CHROMADB_PATH = r'C:\Users\dkitc\.dex-jr\chromadb'
COLLECTIONS = ['dex_canon', 'ddl_archive', 'dex_code', 'ext_creator']

print("Loading corpus metadata...")
c = chromadb.PersistentClient(path=CHROMADB_PATH)

# Build a set of all filenames in the corpus
corpus_files = set()
corpus_detail = {}

for name in COLLECTIONS:
    try:
        col = c.get_collection(name)
        total = col.count()
        # Fetch in batches
        batch_size = 5000
        offset = 0
        while offset < total:
            r = col.get(include=['metadatas'], limit=batch_size, offset=offset)
            for m in r['metadatas']:
                fname = m.get('filename', '')
                if fname:
                    corpus_files.add(fname)
                    corpus_detail[fname] = name
            offset += batch_size
        print(f"  {name}: {total} chunks scanned")
    except Exception as e:
        print(f"  {name}: error - {e}")

print(f"\nTotal unique files in corpus: {len(corpus_files)}")

# Now walk the archive folder
print(f"\nScanning archive: {ARCHIVE_PATH}\n")

found = []
missing = []
EXTENSIONS = {'.txt', '.md', '.pdf', '.docx', '.xlsx', '.json', '.py', '.js', '.jsx', '.ts', '.csv'}

for root, dirs, files in os.walk(ARCHIVE_PATH):
    # Skip hidden folders
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    for fname in files:
        ext = os.path.splitext(fname)[1].lower()
        if ext not in EXTENSIONS:
            continue
        if fname in corpus_files:
            found.append((fname, corpus_detail[fname], root))
        else:
            missing.append((fname, root))

print(f"FILES IN CORPUS:  {len(found)}")
print(f"FILES NOT IN CORPUS: {len(missing)}")

print("\n--- MISSING FROM CORPUS ---")
for fname, folder in sorted(missing):
    rel = folder.replace(ARCHIVE_PATH, '').lstrip('\\')
    print(f"  [{rel}] {fname}")

print("\n--- FOUND IN CORPUS ---")
for fname, collection, folder in sorted(found):
    rel = folder.replace(ARCHIVE_PATH, '').lstrip('\\')
    print(f"  [{collection}] [{rel}] {fname}")
