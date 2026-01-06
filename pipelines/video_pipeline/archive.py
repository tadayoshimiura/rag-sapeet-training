"""圧縮ファイルの展開処理。"""
import os
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import List

from .config import PipelineConfig
from .s3_utils import S3Client
from .media_map import MEDIA_MAP, match_media
ARCHIVE_EXTS = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2")


def unpack_archives(cfg: PipelineConfig) -> List[str]:
    """upload配下のアーカイブを展開し、動画/PDFのみ extracted 配下へ展開する。

    Args:
        cfg: パイプライン設定。

    Returns:
        展開してアップロードしたS3 URIのリスト。
    """
    s3 = S3Client(bucket=cfg.bucket)
    upload_prefix = f"raw/course_packages/{cfg.course_id}/upload/"
    keys = [k for k in s3.list_keys(upload_prefix) if _is_archive(k)]
    uploaded: List[str] = []
    for key in keys:
        uri = f"s3://{cfg.bucket}/{key}"
        with s3.temp_local_copy(uri) as local_archive:
            uploaded.extend(_extract_and_upload(local_archive, cfg))
    return uploaded


def _is_archive(key: str) -> bool:
    return any(key.lower().endswith(ext) for ext in ARCHIVE_EXTS)


def _extract_and_upload(archive_path: str, cfg: PipelineConfig) -> List[str]:
    """アーカイブから動画/PDFを取り出し、extracted/video/pdf にアップロード。"""
    uploaded: List[str] = []
    s3 = S3Client(bucket=cfg.bucket)
    dest_prefixes = {
        media: f"s3://{cfg.bucket}/" + conf["extracted_prefix"].format(course_id=cfg.course_id)
        for media, conf in MEDIA_MAP.items()
    }

    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, "r:*") as tf:
            for member in tf.getmembers():
                if not member.isreg():
                    continue
                rel = _safe_relpath(member.name)
                dest_prefix = _select_prefix(rel, dest_prefixes)
                if not dest_prefix:
                    continue
                with tf.extractfile(member) as src:
                    if src is None:
                        continue
                    with tempfile.NamedTemporaryFile(delete=False) as tmp:
                        tmp.write(src.read())
                        tmp_path = tmp.name
                dest_uri = dest_prefix + rel
                s3.upload_file(tmp_path, dest_uri)
                os.remove(tmp_path)
                uploaded.append(dest_uri)
    elif zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as zf:
            for name in zf.namelist():
                rel = _safe_relpath(name)
                dest_prefix = _select_prefix(rel, dest_prefixes)
                if not dest_prefix:
                    continue
                with zf.open(name) as src, tempfile.NamedTemporaryFile(delete=False) as tmp:
                    tmp.write(src.read())
                    tmp_path = tmp.name
                dest_uri = dest_prefix + rel
                s3.upload_file(tmp_path, dest_uri)
                os.remove(tmp_path)
                uploaded.append(dest_uri)
    else:
        # 非対応形式はスキップ
        pass
    return uploaded


def _safe_relpath(name: str) -> str:
    """アーカイブ内のパスを正規化し、相対パスのみ返す。"""
    rel = Path(name).as_posix()
    # 先頭の ./ を除去
    if rel.startswith("./"):
        rel = rel[2:]
    # 絶対パスや親参照は排除
    rel_path = Path(rel).resolve().relative_to(Path(".").resolve())
    return rel_path.as_posix()


def _select_prefix(rel: str, dest_prefixes: dict) -> str | None:
    media = match_media(rel)
    if not media:
        return None
    return dest_prefixes.get(media)
