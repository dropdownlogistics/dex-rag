import chromadb

c = chromadb.PersistentClient(path=r'C:\Users\dkitc\.dex-jr\chromadb')

for collection_name in ['dex_canon', 'ddl_archive']:
    try:
        col = c.get_collection(collection_name)
        r = col.get(include=['metadatas'], limit=1000)
        matches = [m for m in r['metadatas'] if 'DexJr_LaunchKit_v2.0' in str(m.get('filename', ''))]
        print(f"{collection_name}: {len(matches)} chunks found")
        if matches:
            print(f"  Sample: {matches[0]}")
    except Exception as e:
        print(f"{collection_name}: error - {e}")
