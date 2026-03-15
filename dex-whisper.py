#!/usr/bin/env python3
"""
DEX JR. WHISPER PIPELINE
Batch transcription of video/audio files using OpenAI Whisper.
Outputs .txt canon documents with metadata headers for ingest.

Usage:
  python dex-whisper.py --dir "C:\\Users\\dexjr\\dex-rag\\tiktok"
  python dex-whisper.py --dir "C:\\path\\to\\videos" --model medium
  python dex-whisper.py --dir "C:\\path\\to\\videos" --skip-existing

Output: C:\\Users\\dexjr\\99_DexUniverseArchive\\00_Archive\\DDL-Standards-Canon\\video_transcripts\\tiktok\\

Dropdown Logistics -- Chaos -> Structured -> Automated
STD-WHISPER-001 | 2026-03-08
"""
import os
import sys
import argparse
import datetime
import whisper

# -----------------------------
# CONFIG
# -----------------------------
DEFAULT_INPUT_DIR  = r"C:\Users\dexjr\dex-rag\tiktok"
DEFAULT_OUTPUT_DIR = r"C:\Users\dexjr\99_DexUniverseArchive\00_Archive\DDL-Standards-Canon\video_transcripts\tiktok"
DEFAULT_MODEL      = "base"

SUPPORTED_EXTENSIONS = {".mp4", ".mp3", ".m4a", ".mov", ".wav", ".webm"}

# -----------------------------
# HEADER BUILDER
# -----------------------------
def build_header(filename, language, duration_seconds, model_used):
    now = datetime.datetime.now().isoformat()
    return f"""# =====================================================================
# DEX JR. VIDEO TRANSCRIPT
# =====================================================================
# source_file:       {filename}
# source_type:       video_transcript
# origin:            tiktok_public
# platform:          tiktok
# account:           @dropdownlogistics
# era:               pre_dexverse
# confidence:        whisper_auto
# processing_stage:  unstructured
# language:          {language}
# duration_seconds:  {duration_seconds:.1f}
# whisper_model:     {model_used}
# transcribed_at:    {now}
# tier:              foundation
# status:            pre_canonical
# =====================================================================

"""

# -----------------------------
# MAIN
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Dex Jr Whisper Batch Transcription Pipeline")
    parser.add_argument("--dir",           default=DEFAULT_INPUT_DIR,  help="Directory containing video files")
    parser.add_argument("--output",        default=DEFAULT_OUTPUT_DIR, help="Output directory for transcripts")
    parser.add_argument("--model",         default=DEFAULT_MODEL,      help="Whisper model: tiny, base, small, medium, large")
    parser.add_argument("--skip-existing", action="store_true",        help="Skip files that already have a transcript")
    parser.add_argument("--language",      default=None,               help="Force language (e.g. en). Auto-detect if not set.")
    args = parser.parse_args()

    input_dir  = args.dir
    output_dir = args.output

    os.makedirs(output_dir, exist_ok=True)

    # Scan for video files
    files = [
        f for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
    ]
    files.sort()
    total = len(files)

    print("\n" + "=" * 60)
    print("  DEX JR. WHISPER PIPELINE")
    print(f"  Input:  {input_dir}")
    print(f"  Output: {output_dir}")
    print(f"  Model:  {args.model}")
    print(f"  Files:  {total}")
    print("=" * 60)

    if total == 0:
        print("\n  No supported video files found. Exiting.")
        return

    print(f"\n  Loading Whisper model: {args.model}...")
    model = whisper.load_model(args.model)
    print("  Model loaded.\n")

    skipped   = 0
    errors    = 0
    completed = 0
    start     = datetime.datetime.now()

    for i, filename in enumerate(files):
        input_path  = os.path.join(input_dir, filename)
        stem        = os.path.splitext(filename)[0]
        # Sanitize filename for output
        safe_stem   = "".join(c if c.isalnum() or c in " _-" else "_" for c in stem).strip()
        output_path = os.path.join(output_dir, f"{safe_stem}.txt")

        print(f"  [{i+1}/{total}] {filename[:60]}")

        if args.skip_existing and os.path.exists(output_path):
            print(f"    -> SKIP (transcript exists)")
            skipped += 1
            continue

        try:
            transcribe_args = {"verbose": False}
            if args.language:
                transcribe_args["language"] = args.language

            result = model.transcribe(input_path, **transcribe_args)

            language = result.get("language", "unknown")
            segments = result.get("segments", [])
            duration = segments[-1]["end"] if segments else 0.0
            text     = result.get("text", "").strip()

            if not text or len(text) < 20:
                print(f"    -> SKIP (transcript too short: {len(text)} chars)")
                skipped += 1
                continue

            header  = build_header(filename, language, duration, args.model)
            content = header + text + "\n"

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)

            completed += 1
            print(f"    -> OK  [{language}] {duration:.1f}s | {len(text)} chars")

        except Exception as e:
            errors += 1
            print(f"    -> ERROR: {e}")

    elapsed = (datetime.datetime.now() - start).total_seconds()

    print("\n" + "=" * 60)
    print("  WHISPER PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Completed: {completed}")
    print(f"  Skipped:   {skipped}")
    print(f"  Errors:    {errors}")
    print(f"  Time:      {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  Output:    {output_dir}")
    print("\n  Next step: run dex-ingest.py --path <output_dir> --build-canon")
    print("=" * 60)

if __name__ == "__main__":
    main()
