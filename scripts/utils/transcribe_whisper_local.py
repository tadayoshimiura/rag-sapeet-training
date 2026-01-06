"""
Local Whisper transcription (open-source) for audio files.

Prerequisites (once network is allowed):
  pip install -U openai-whisper torch
  # macOS/Linux: ensure ffmpeg is installed (brew install ffmpeg, etc.)

Usage:
  python3 scripts/utils/transcribe_whisper_local.py \
      --input-dir data/mv/python初級 \
      --output-dir data/text/audio_local/python初級 \
      --model small
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

import whisper


def find_audio_files(root: Path) -> list[Path]:
    exts = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg"}
    return sorted(p for p in root.iterdir() if p.suffix.lower() in exts)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcribe audio files locally with Whisper.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/mv/python初級"),
        help="Directory containing audio files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/text/audio_local/python初級"),
        help="Directory to write transcripts.",
    )
    parser.add_argument(
        "--model",
        default="small",
        help="Whisper model size (tiny, base, small, medium, large).",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing transcripts.")
    parser.add_argument(
        "--language",
        default=None,
        help="Language code (e.g., ja). If omitted, Whisper will auto-detect.",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])

    if not args.input_dir.exists():
        sys.exit(f"Input dir not found: {args.input_dir}")
    audio_files = find_audio_files(args.input_dir)
    if not audio_files:
        sys.exit(f"No audio files in {args.input_dir}")

    model = whisper.load_model(args.model)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for audio_path in audio_files:
        out_path = args.output_dir / (audio_path.stem + ".txt")
        if out_path.exists() and not args.overwrite:
            print(f"Skip existing {out_path}")
            continue
        result = model.transcribe(str(audio_path), language=args.language)
        out_path.write_text(result["text"] + "\n", encoding="utf-8")
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
