import chromadb
import os

ARCHIVE_PATH = r'C:\Users\dexjr\99_DexUniverseArchive'
CHROMADB_PATH = r'C:\Users\dkitc\.dex-jr\chromadb'
COLLECTIONS = ['dex_canon', 'ddl_archive', 'dex_code', 'ext_creator']

# Skip these folders — they're code repos, not DDL lore
SKIP_FOLDERS = {
    '97_Repos_Curated',
    'langchain',
    'semantic-kernel',
    'ollama',
}

print("Loading corpus metadata...")
c = chromadb.PersistentClient(path=CHROMADB_PATH)

corpus_files = set()

for name in COLLECTIONS:
    try:
        col = c.get_collection(name)
        total = col.count()
        batch_size = 5000
        offset = 0
        while offset < total:
            r = col.get(include=['metadatas'], limit=batch_size, offset=offset)
            for m in r['metadatas']:
                fname = m.get('filename', '')
                if fname:
                    corpus_files.add(fname)
            offset += batch_size
        print(f"  {name}: {total} chunks scanned")
    except Exception as e:
        print(f"  {name}: error - {e}")

print(f"\nTotal unique filenames in corpus: {len(corpus_files)}")
print(f"\nScanning archive (skipping code repos)...\n")

EXTENSIONS = {'.txt', '.md', '.pdf', '.docx', '.xlsx', '.json', '.csv'}

found_count = 0
missing = []

for root, dirs, files in os.walk(ARCHIVE_PATH):
    # Skip hidden and known code repo folders
    dirs[:] = [d for d in dirs 
               if not d.startswith('.') 
               and d not in SKIP_FOLDERS]
    
    for fname in files:
        ext = os.path.splitext(fname)[1].lower()
        if ext not in EXTENSIONS:
            continue
        
        if fname in corpus_files:
            found_count += 1
        else:
            rel = root.replace(ARCHIVE_PATH, '').lstrip('\\')
            missing.append((rel, fname))

print(f"IN CORPUS:      {found_count}")
print(f"MISSING:        {len(missing)}")
print(f"TOTAL SCANNED:  {found_count + len(missing)}")

if missing:
    print(f"\n--- MISSING FROM CORPUS ({len(missing)} files) ---")
    # Group by folder
    by_folder = {}
    for folder, fname in sorted(missing):
        by_folder.setdefault(folder, []).append(fname)
    
    for folder, files in sorted(by_folder.items()):
        print(f"\n  [{folder}]")
        for f in files:
            print(f"    - {f}")

print("\nDone.")
