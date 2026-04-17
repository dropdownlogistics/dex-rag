r"""
dex-ocr.py -- Screenshot OCR pipeline for Dex Jr. RAG corpus
Converts images to searchable .txt files for canon ingestion.

Usage:
  python dex-ocr.py --dir "C:/path/to/screenshots"
  python dex-ocr.py --dir "C:/path/to/screenshots" --ingest
  python dex-ocr.py --dir "C:/path/to/screenshots" --preview
  python dex-ocr.py --dir "C:/path/to/screenshots" --skip-processed

Snippet: dex-ocr -- cd C:/Users/dexjr/dex-rag; python dex-ocr.py
"""

import argparse
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image
    import pytesseract
except ImportError:
    print("ERROR: Required packages missing. Run:")
    print("  pip install pytesseract Pillow --break-system-packages")
    sys.exit(1)

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ── CONFIG ────────────────────────────────────────────────────────────────────

DEFAULT_OUT_DIR = r"C:\Users\dexjr\99_DexUniverseArchive\00_Archive\DDL-Standards-Canon"
INGEST_SCRIPT   = r"C:\Users\dexjr\dex-rag\dex-ingest.py"
CANON_PATH      = DEFAULT_OUT_DIR
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
LOG_FILE        = r"C:\Users\dexjr\dex-rag\dex-ocr-log.txt"

# ── HELPERS ───────────────────────────────────────────────────────────────────

def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


def get_image_files(directory: str) -> list[Path]:
    dir_path = Path(directory)
    if not dir_path.exists():
        print(f"ERROR: Directory not found: {directory}")
        sys.exit(1)
    files = [
        f for f in dir_path.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return sorted(files)


def output_filename(image_path: Path) -> str:
    return f"OCR_{image_path.stem}.txt"


def already_processed(image_path: Path, out_dir: Path) -> bool:
    return (out_dir / output_filename(image_path)).exists()


def build_header(image_path: Path, img: Image.Image) -> str:
    width, height = img.size
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"SOURCE: {image_path.name}\n"
        f"FULL_PATH: {image_path.resolve()}\n"
        f"DIMENSIONS: {width}x{height}px\n"
        f"OCR_TIMESTAMP: {timestamp}\n"
        f"TYPE: screenshot\n"
        f"{'=' * 60}\n\n"
    )


def run_ocr(image_path: Path) -> tuple[str, str | None]:
    """Returns (text, error). error is None on success."""
    try:
        img = Image.open(image_path)
        # Convert to RGB if needed (handles RGBA, palette mode, etc.)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        text = pytesseract.image_to_string(img, config="--psm 3")
        header = build_header(image_path, img)
        full_text = header + text.strip()
        return full_text, None
    except Exception as e:
        return "", str(e)


def save_txt(content: str, out_path: Path):
    out_path.write_text(content, encoding="utf-8")


def trigger_ingest():
    print("\n  Triggering canon ingestion...")
    result = subprocess.run(
        [sys.executable, INGEST_SCRIPT,
         "--path", CANON_PATH, "--build-canon"],
        capture_output=False
    )
    if result.returncode != 0:
        print("  WARNING: Ingest returned non-zero exit code.")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="dex-ocr.py — Convert screenshots to .txt for Dex Jr. RAG corpus"
    )
    parser.add_argument("--dir",             required=True,  help="Input folder of images")
    parser.add_argument("--out-dir",         default=DEFAULT_OUT_DIR, help="Output folder for .txt files")
    parser.add_argument("--ingest",          action="store_true", help="Trigger canon ingestion after conversion")
    parser.add_argument("--preview",         action="store_true", help="Print OCR output without saving")
    parser.add_argument("--skip-processed",  action="store_true", help="Skip files already converted")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    if not args.preview:
        out_dir.mkdir(parents=True, exist_ok=True)

    images = get_image_files(args.dir)
    total = len(images)

    if total == 0:
        print(f"No image files found in: {args.dir}")
        sys.exit(0)

    print(f"\n  dex-ocr.py — Screenshot OCR Pipeline")
    print(f"  {'=' * 60}")
    print(f"  Input:    {args.dir}")
    print(f"  Output:   {args.out_dir}")
    print(f"  Images:   {total}")
    print(f"  Mode:     {'PREVIEW' if args.preview else 'SAVE'}")
    print(f"  {'=' * 60}\n")

    processed = 0
    skipped   = 0
    failed    = 0
    empty     = 0

    for i, image_path in enumerate(images, 1):
        label = f"[{i}/{total}]"

        # Skip if already processed
        if args.skip_processed and not args.preview:
            if already_processed(image_path, out_dir):
                print(f"  {label} SKIP (exists) — {image_path.name}")
                skipped += 1
                continue

        # Run OCR
        text, error = run_ocr(image_path)

        if error:
            print(f"  {label} ERROR — {image_path.name}: {error}")
            log(f"ERROR {image_path.name}: {error}")
            failed += 1
            continue

        # Check for meaningful content
        body = text.split("=" * 60)[-1].strip() if "=" * 60 in text else text.strip()
        if len(body) < 20:
            print(f"  {label} EMPTY — {image_path.name} (no readable text)")
            empty += 1
            log(f"EMPTY {image_path.name}: OCR returned < 20 chars")
            continue

        out_name = output_filename(image_path)

        if args.preview:
            print(f"\n  {label} PREVIEW — {image_path.name}")
            print(f"  {'-' * 40}")
            preview_text = body[:300] + ("..." if len(body) > 300 else "")
            print(f"  {preview_text}\n")
        else:
            out_path = out_dir / out_name
            save_txt(text, out_path)
            print(f"  {label} {image_path.name} → {out_name}")
            log(f"OK {image_path.name} → {out_name} ({len(body)} chars)")
            processed += 1

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print(f"\n  {'=' * 60}")
    print(f"  OCR COMPLETE")
    print(f"  {'=' * 60}")
    print(f"  Processed:  {processed}")
    print(f"  Skipped:    {skipped}")
    print(f"  Empty:      {empty}")
    print(f"  Failed:     {failed}")
    print(f"  Total:      {total}")
    if not args.preview:
        print(f"  Output:     {args.out_dir}")
    print(f"  Log:        {LOG_FILE}")
    print(f"  {'=' * 60}\n")

    # ── INGEST ────────────────────────────────────────────────────────────────
    if args.ingest and not args.preview and processed > 0:
        trigger_ingest()


if __name__ == "__main__":
    main()
