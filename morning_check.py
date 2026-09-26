import chromadb
import os

CHROMADB_PATH = r'C:\Users\dkitc\.dex-jr\chromadb'
TRANSCRIPT_FOLDER = r'C:\Users\dkitc\OneDrive\DDL_Ingest\Mania\transcripts'

# Corpus chunk counts
print("=== CORPUS STATE ===")
c = chromadb.PersistentClient(path=CHROMADB_PATH)
total = 0
for name in ['dex_canon', 'ddl_archive', 'dex_code', 'ext_creator']:
    try:
        count = c.get_collection(name).count()
        total += count
        print(f"  {name}: {count:,}")
    except Exception as e:
        print(f"  {name}: error - {e}")
print(f"  TOTAL: {total:,}")

# Transcript progress
print("\n=== WHISPER PROGRESS ===")
if os.path.exists(TRANSCRIPT_FOLDER):
    transcripts = [f for f in os.listdir(TRANSCRIPT_FOLDER) if f.endswith('.txt')]
    print(f"  Transcripts completed: {len(transcripts)}")
    for t in sorted(transcripts):
        size = os.path.getsize(os.path.join(TRANSCRIPT_FOLDER, t))
        print(f"    {t} ({size:,} bytes)")
else:
    print(f"  Folder not found: {TRANSCRIPT_FOLDER}")
