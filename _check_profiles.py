import chromadb
c = chromadb.PersistentClient(path=r'C:\Users\dkitc\.dex-jr\chromadb')
for name in ['dex_canon','dex_canon_v2','ddl_archive','ddl_archive_v2','dex_code','dex_code_v2']:
    col = c.get_collection(name)
    r = col.get(where_document={'$contains':'PROFILE-DDL-DAVE-KITCHENS-001'},limit=5)
    print(name, len(r['ids']))
