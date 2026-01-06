#!/usr/bin/env python3
"""コース単位の処理（差分検知/処理実行）をまとめて実行する。"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import argparse
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import boto3

from pipelines.video_pipeline.config import PipelineConfig
from pipelines.video_pipeline.pipeline import VideoPipeline
from pipelines.video_pipeline.lecture_map import resolve_lecture_from_source
from pipelines.video_pipeline.s3_utils import S3Client
from pipelines.video_pipeline.archive import unpack_archives


@dataclass
class InputObject:
    uri: str
    key: str
    etag: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="講座フォルダ（raw/upload）配下の動画・PDF・CSVを検知し、差分があるものだけ処理する。",
        epilog=(
            "例:\n"
            "  PYTHONPATH=$PWD AWS_PROFILE=... AWS_REGION=ap-northeast-1 "
            "python scripts/entry/run_course_pipeline.py --bucket rag-dev-intloop-20251217 --course-id course_id=test_00\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--bucket", required=True, help="対象S3バケット名。")
    parser.add_argument("--course-id", required=True, help="講座ID（course_id=... 形式）。")
    parser.add_argument("--resume-failed", action="store_true", help="動画ASRで、前回失敗チャンクのみ再実行する。")
    parser.add_argument(
        "--unpack-archives",
        action="store_true",
        help="upload配下に zip/tar がある場合、動画/PDFのみ抽出して extracted に配置する。",
    )
    parser.add_argument(
        "--only-changed",
        action="store_true",
        default=True,
        help="差分（ETag変化 or 未処理）だけ処理する。デフォルト有効。",
    )
    parser.add_argument(
        "--process-all",
        action="store_true",
        help="差分判定を無視して全件処理する（デバッグ用）。",
    )
    parser.add_argument("--limit", type=int, default=None, help="処理件数の上限（先頭から）。")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cfg = PipelineConfig(
        bucket=args.bucket,
        course_id=args.course_id,
        bedrock_region=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
    )
    pipeline = VideoPipeline(cfg)

    if args.unpack_archives:
        unpack_archives(cfg)

    inputs = detect_upload_inputs(cfg)
    if not inputs:
        raise SystemExit("upload配下に動画(.mp4/.mov/.mkv/.webm) または PDF(.pdf) が見つかりませんでした。")

    status = pipeline.load_status_document()
    seen = 0
    processed = 0
    for obj in inputs:
        if args.limit is not None and seen >= args.limit:
            break
        seen += 1
        if args.process_all:
            should = True
        elif args.only_changed:
            should = should_process(status, obj)
        else:
            should = True

        if not should:
            # 差分が無くても、メタ情報ヘッダが無ければ追記する（LLMを呼ばない軽量更新）
            prev = (status.get("files") or {}).get(obj.uri) or {}
            md_uri = prev.get("markdown") or ""
            if md_uri:
                key_lower = obj.key.lower()
                if key_lower.endswith(".pdf"):
                    source = "pdf"
                elif key_lower.endswith(".csv"):
                    source = "csv"
                else:
                    source = "mv"
                _, lecture_id = resolve_lecture_from_source(cfg, obj.uri, fallback=pipeline._infer_category(obj.uri))
                try:
                    # メタの category は論理カテゴリ（既定: unclassified）とし、rawフォルダ名に依存しない
                    updated = pipeline.ensure_markdown_metadata(
                        md_uri,
                        source=source,
                        category=None,
                        source_uri=obj.uri,
                        lecture_id=lecture_id,
                    )
                    if updated:
                        logging.info("backfill metadata: %s", md_uri)
                except Exception as e:  # noqa: BLE001
                    logging.warning("metadata backfill failed: %s (%s)", md_uri, e)
            logging.info("skip (no change): %s", obj.uri)
            continue

        logging.info("process: %s", obj.uri)
        try:
            key_lower = obj.key.lower()
            if key_lower.endswith(".pdf"):
                out = pipeline.run_for_pdf(obj.uri)
            elif key_lower.endswith(".csv"):
                out = pipeline.run_for_csv(obj.uri)
            else:
                out = pipeline.run_for_movie(obj.uri, resume_failed=args.resume_failed)
            # 成功時のファイル状態を更新（ETagはここで記録）
            pipeline.update_file_status(obj.uri, etag=obj.etag, markdown_uri=out, errors=[])
            logging.info("done: %s -> %s", obj.uri, out)
        except Exception as e:  # noqa: BLE001
            pipeline.update_file_status(obj.uri, etag=obj.etag, markdown_uri="", errors=[str(e)])
            logging.error("failed: %s (%s)", obj.uri, e)
        processed += 1


def detect_upload_inputs(cfg: PipelineConfig) -> List[InputObject]:
    """raw/upload配下の動画・PDF・CSVを列挙し、ETag付きで返す。"""
    s3 = S3Client(bucket=cfg.bucket)
    upload_prefix = f"raw/course_packages/{cfg.course_id}/upload/"
    keys = s3.list_keys(upload_prefix)
    # アーカイブ展開後に extracted に入ったものも対象にする（upload直下に動画がない場合の救済）
    keys += s3.list_keys(f"processed/{cfg.course_id}/extracted/video/")
    keys += s3.list_keys(f"processed/{cfg.course_id}/extracted/pdf/")

    exts = (".mp4", ".mov", ".mkv", ".webm", ".pdf", ".csv")
    objs: List[InputObject] = []
    for key in sorted(keys):
        if not key.lower().endswith(exts):
            continue
        uri = f"s3://{cfg.bucket}/{key}"
        head = s3.head(uri)
        objs.append(InputObject(uri=uri, key=key, etag=head.get("etag", "")))
    return objs


def should_process(status_doc: Dict, obj: InputObject) -> bool:
    """ETagを基準に差分判定する。未処理・前回エラー・ETag変化なら処理。"""
    files = status_doc.get("files") or {}
    prev = files.get(obj.uri)
    if not prev:
        return True
    if prev.get("etag") != obj.etag:
        return True
    if prev.get("errors"):
        return True
    if not prev.get("markdown"):
        return True
    return False


if __name__ == "__main__":
    main()
