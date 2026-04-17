import os
import subprocess
import sys

MANIA_FOLDER = r'C:\Users\dkitc\OneDrive\DDL_Ingest\Mania'
OUTPUT_FOLDER = os.path.join(MANIA_FOLDER, 'transcripts')
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

EXTENSIONS = {'.m4a', '.mp3', '.wav', '.mp4', '.mov'}

# Find all audio files
files = []
for root, dirs, filenames in os.walk(MANIA_FOLDER):
    dirs[:] = [d for d in dirs if d != 'transcripts']
    for f in filenames:
        if os.path.splitext(f)[1].lower() in EXTENSIONS:
            files.append(os.path.join(root, f))

if not files:
    print(f"No audio files found in {MANIA_FOLDER}")
    sys.exit(0)

# Check which are already done - skip them
already_done = set()
for f in os.listdir(OUTPUT_FOLDER):
    if f.endswith('.txt'):
        already_done.add(os.path.splitext(f)[0])

pending = []
for filepath in files:
    basename = os.path.splitext(os.path.basename(filepath))[0]
    if basename in already_done:
        print(f"  SKIP (already done): {os.path.basename(filepath)}")
    else:
        pending.append(filepath)

print(f"Found {len(files)} total files")
print(f"Already transcribed: {len(already_done)}")
print(f"Remaining: {len(pending)}")

if not pending:
    print("All files already transcribed!")
    sys.exit(0)

success = []
failed = []

for i, filepath in enumerate(pending, 1):
    filename = os.path.basename(filepath)
    print(f"[{i}/{len(pending)}] Transcribing: {filename}")

    try:
        result = subprocess.run(
            [
                'whisper', filepath,
                '--model', 'medium',
                '--output_format', 'txt',
                '--output_dir', OUTPUT_FOLDER,
                '--language', 'en',
                '--device', 'cuda'
            ],
            capture_output=True,
            text=True,
            timeout=14400,
            encoding='utf-8',
            errors='replace'
        )

        if result.returncode == 0:
            print(f"  [DONE]")
            success.append(filename)
        else:
            print(f"  [FAILED]: {result.stderr[:200]}")
            failed.append(filename)

    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT] after 4 hours")
        failed.append(filename)
    except Exception as e:
        print(f"  [ERROR]: {e}")
        failed.append(filename)

print(f"COMPLETE: {len(success)} succeeded, {len(failed)} failed")
if failed:
    print("Failed files:")
    for f in failed:
        print(f"  - {f}")
print(f"Transcripts saved to: {OUTPUT_FOLDER}")
