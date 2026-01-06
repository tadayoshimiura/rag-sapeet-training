"""出力ファイルの書き込み補助。"""
import json
import tempfile
from pathlib import Path
from typing import Any, Tuple

from shared.s3_utils import S3Client, parse_s3_uri


def is_s3_uri(path: str) -> bool:
    return path.startswith("s3://")


def split_s3_uri(path: str) -> Tuple[str, str]:
    return parse_s3_uri(path)


def basename(path: str) -> str:
    if is_s3_uri(path):
        _, key = split_s3_uri(path)
        return key.rsplit("/", 1)[-1]
    return Path(path).name


def append_suffix(path: str, suffix: str) -> str:
    return f"{path}{suffix}"


def write_text(path: str, text: str) -> None:
    if is_s3_uri(path):
        bucket, _ = split_s3_uri(path)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp") as tmp:
            tmp_path = tmp.name
        try:
            Path(tmp_path).write_text(text, encoding="utf-8")
            S3Client(bucket=bucket).upload_file(tmp_path, path)
        finally:
            try:
                Path(tmp_path).unlink()
            except FileNotFoundError:
                pass
    else:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")


def write_json(path: str, payload: Any) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
