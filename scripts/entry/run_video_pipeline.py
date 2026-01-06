#!/usr/bin/env python3
"""
単体の動画（または upload 配下の全動画）を処理するための簡易CLI。
既存RAG用のコード・データは汚さない（別システムとして独立）。
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import argparse
import logging
from typing import Optional

from pipelines.video_pipeline.config import PipelineConfig
from pipelines.video_pipeline.pipeline import VideoPipeline
from pipelines.video_pipeline.s3_utils import S3Client
from pipelines.video_pipeline.archive import unpack_archives


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", default="bucket")
    parser.add_argument("--course-id", default="course_id=test_00")
    parser.add_argument(
        "--movie-uri",
        help="s3://bucket/path/to/movie.mp4 (未指定なら upload 配下の全動画を検出して順次処理)",
    )
    parser.add_argument("--asr-mode", choices=["whisper", "faster-whisper"], default="whisper")
    parser.add_argument("--asr-model", default="base")
    parser.add_argument("--bedrock-model-id", default=None, help="BedrockモデルID（未指定なら設定のデフォルト）")
    parser.add_argument("--bedrock-region", default=None, help="Bedrockリージョン（未指定ならAWS_REGION）")
    parser.add_argument("--resume-failed", action="store_true", help="前回失敗したチャンクのみ再ASRする")
    parser.add_argument("--unpack-archives", action="store_true", help="upload配下のアーカイブ(zip/tar)を展開して処理する")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = PipelineConfig(
        bucket=args.bucket,
        course_id=args.course_id,
        asr_mode=args.asr_mode,
        asr_model=args.asr_model,
        bedrock_model_id=args.bedrock_model_id or PipelineConfig().bedrock_model_id,
        bedrock_region=args.bedrock_region,
    )
    pipeline = VideoPipeline(cfg)

    if args.unpack_archives:
        unpack_archives(cfg)

    movie_uris = [args.movie_uri] if args.movie_uri else detect_movies(cfg)
    if not movie_uris:
        raise SystemExit("動画が見つかりませんでした（upload配下に mp4/mov/mkv/webm が必要）")

    for uri in movie_uris:
        logging.info("process movie: %s", uri)
        md_uri = pipeline.run_for_movie(uri, resume_failed=args.resume_failed)
        print(md_uri)


def detect_movies(cfg: PipelineConfig) -> list[str]:
    """uploadおよびextracted/video配下の動画を検出し、全件のS3 URIを返す。"""
    s3 = S3Client(bucket=cfg.bucket)
    prefix = f"raw/course_packages/{cfg.course_id}/upload/"
    keys = s3.list_keys(prefix)
    keys += s3.list_keys(f"processed/{cfg.course_id}/extracted/video/")
    exts = (".mp4", ".mov", ".mkv", ".webm")
    uris: list[str] = []
    for key in sorted(keys):
        if key.lower().endswith(exts):
            uris.append(f"s3://{cfg.bucket}/{key}")
    return uris


if __name__ == "__main__":
    main()
