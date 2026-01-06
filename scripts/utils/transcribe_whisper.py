"""
Prepare OpenAI Whisper API transcription for local audio files.

Usage:
  python3 scripts/utils/transcribe_whisper.py \
      --input-dir data/mv/python初級 \
      --output-dir data/text/audio/python初級

Notes:
- Requires `openai` package (>=1.0) and OPENAI_API_KEY in environment.
- Does not run without network access; ready to execute once allowed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from openai import OpenAI


def find_audio_files(root: Path) -> list[Path]:
    """Return audio files under root (common formats)."""
    exts = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg"}
    return sorted(p for p in root.iterdir() if p.suffix.lower() in exts)


def transcribe_file(client: OpenAI, audio_path: Path, output_path: Path, model: str) -> None:
    """Call Whisper API and write transcript to output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with audio_path.open("rb") as audio_file:
        resp = client.audio.transcriptions.create(model=model, file=audio_file)
    output_path.write_text(resp.text + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")


def run(input_dir: Path, output_dir: Path, model: str, overwrite: bool) -> None:
    if not input_dir.exists():
        sys.exit(f"Input dir not found: {input_dir}")
    files = find_audio_files(input_dir)
    if not files:
        sys.exit(f"No audio files in {input_dir}")

    client = OpenAI()
    for audio_path in files:
        out_path = output_dir / (audio_path.stem + ".txt")
        if out_path.exists() and not overwrite:
            print(f"Skip existing {out_path}")
            continue
        transcribe_file(client, audio_path, out_path, model)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcribe audio files with OpenAI Whisper API.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/mv/python初級"),
        help="Directory containing audio files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/text/audio/python初級"),
        help="Directory to write transcripts.",
    )
    parser.add_argument("--model", default="whisper-1", help="Whisper model name.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing transcripts.")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])
    run(args.input_dir, args.output_dir, args.model, args.overwrite)


if __name__ == "__main__":
    main()
