#!/usr/bin/env python3
"""Bedrock Knowledge Bases の取り込みジョブを起動する。"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from __future__ import annotations

import argparse
import os
import time

import boto3


def _load_env_file(path: str) -> None:
    """簡易的に env ファイルを読み込む。"""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def _require_env(name: str) -> str:
    """必須の環境変数を取得する。"""
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} が未設定です")
    return value


def _wait_for_completion(client, kb_id: str, ds_id: str, job_id: str, interval_s: int) -> str:
    """取り込み完了まで待機する。"""
    while True:
        resp = client.get_ingestion_job(
            knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job_id
        )
        status = resp.get("ingestionJob", {}).get("status", "UNKNOWN")
        if status in {"COMPLETE", "FAILED", "STOPPED"}:
            return status
        time.sleep(interval_s)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bedrock Knowledge Bases の取り込みを実行する")
    parser.add_argument(
        "--env",
        default="configs/bedrock_kb_config.env",
        help="KB ID を格納した env ファイル",
    )
    parser.add_argument("--kb-id", default=None, help="Knowledge Base ID（未指定なら env）")
    parser.add_argument("--data-source-id", default=None, help="Data Source ID（未指定なら env）")
    parser.add_argument("--wait", action="store_true", help="完了まで待機する")
    parser.add_argument("--poll-interval", type=int, default=10, help="待機中の確認間隔（秒）")
    args = parser.parse_args()

    _load_env_file(args.env)
    kb_id = args.kb_id or _require_env("KB_ID")
    ds_id = args.data_source_id or _require_env("DATA_SOURCE_ID")

    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        raise SystemExit("AWS_REGION が未設定です")

    client = boto3.client("bedrock-agent", region_name=region)
    resp = client.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
    job_id = resp.get("ingestionJob", {}).get("ingestionJobId", "")
    if not job_id:
        raise SystemExit("ingestionJobId が取得できませんでした")
    print(f"started ingestion: job_id={job_id}")

    if args.wait:
        status = _wait_for_completion(client, kb_id, ds_id, job_id, args.poll_interval)
        print(f"ingestion status: {status}")


if __name__ == "__main__":
    main()
