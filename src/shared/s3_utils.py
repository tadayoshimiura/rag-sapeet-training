"""S3操作ユーティリティ。"""
import contextlib
import os
import tempfile
from dataclasses import dataclass
from typing import Iterator, List, Tuple

import boto3


def parse_s3_uri(uri: str) -> Tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"S3 URIではありません: {uri}")
    without_scheme = uri[len("s3://") :]
    parts = without_scheme.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"S3 URIの形式が不正です: {uri}")
    bucket, key = parts
    return bucket, key


@dataclass
class S3Client:
    bucket: str

    def __post_init__(self) -> None:
        self._client = boto3.client("s3")

    def upload_file(self, src_path: str, dest_uri: str) -> None:
        bucket, key = parse_s3_uri(dest_uri)
        self._client.upload_file(src_path, bucket, key)

    def download_file(self, src_uri: str, dest_path: str) -> None:
        bucket, key = parse_s3_uri(src_uri)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        self._client.download_file(bucket, key, dest_path)

    def list_keys(self, prefix: str) -> List[str]:
        """指定プレフィックス配下のオブジェクトキーを列挙する。

        Args:
            prefix: 取得対象のプレフィックス。

        Returns:
            キーのリスト。
        """
        keys: List[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def head(self, uri: str) -> dict:
        """S3オブジェクトのメタ情報（ETag等）を取得する。"""
        bucket, key = parse_s3_uri(uri)
        resp = self._client.head_object(Bucket=bucket, Key=key)
        etag = (resp.get("ETag") or "").strip('"')
        last_modified = resp.get("LastModified")
        return {
            "etag": etag,
            "size": resp.get("ContentLength"),
            "last_modified": last_modified.isoformat() if last_modified else None,
        }

    def read_prefix_text(self, uri: str, max_bytes: int = 2048) -> str:
        """S3オブジェクトの先頭だけを読み、UTF-8文字列として返す。

        Args:
            uri: 対象S3 URI。
            max_bytes: 先頭から読む最大バイト数。

        Returns:
            UTF-8文字列（デコード不能な場合は置換）。
        """
        bucket, key = parse_s3_uri(uri)
        resp = self._client.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{max_bytes-1}")
        body = resp["Body"].read()
        return body.decode("utf-8", errors="replace")

    @contextlib.contextmanager
    def temp_local_copy(self, src_uri: str) -> Iterator[str]:
        """S3オブジェクトを一時ファイルにダウンロードし、パスを返す。

        Args:
            src_uri: ダウンロード元のS3 URI。

        Yields:
            ローカル一時ファイルのパス。
        """
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        try:
            self.download_file(src_uri, tmp_path)
            yield tmp_path
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.remove(tmp_path)
