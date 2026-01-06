"""講座/講義のマッピング。"""
from __future__ import annotations

from pathlib import Path

from .config import PipelineConfig
from .s3_utils import parse_s3_uri


MEDIA_DIR_NAMES = {
    "動画",
    "pdf",
    "PDF",
    "音声",
    "テキスト",
    "video",
    "movie",
    "audio",
    "html",
}


def resolve_lecture_from_source(
    cfg: PipelineConfig,
    source_uri: str,
    fallback: str | None = None,
) -> tuple[str, str]:
    """source_uri から course_id / lecture_id を解決する（フォルダ構成のみ）。"""
    inferred = _infer_lecture_from_upload(source_uri)
    if inferred:
        return cfg.course_id, inferred
    if fallback:
        return cfg.course_id, fallback
    return cfg.course_id, "unknown"


def infer_lecture_from_kb_path(kb_path: str) -> str | None:
    """knowledge_md/v1 配下のパスから lecture_id を推定する。"""
    path = Path(kb_path)
    parts = [p for p in path.parts]
    if "knowledge_md" in parts:
        idx = parts.index("knowledge_md")
        if idx + 2 < len(parts) and parts[idx + 1] == "v1":
            sub = parts[idx + 2 :]
            if path.is_file() and sub:
                sub = sub[:-1]
            if sub:
                return "/".join(sub).strip("/")
    # 知識フォルダでなければ親ディレクトリ名を使う
    if path.is_dir():
        return path.name
    return path.parent.name if path.parent else None


def _normalize_s3_key(source_uri: str) -> str:
    if source_uri.startswith("s3://"):
        _, key = parse_s3_uri(source_uri)
        return key
    return source_uri


def _extract_upload_subpath(key: str, keep_filename: bool) -> str:
    parts = key.split("/")
    if "upload" not in parts:
        return ""
    idx = parts.index("upload")
    if keep_filename:
        sub = parts[idx + 1 :]
    else:
        sub = parts[idx + 1 : -1]
    return "/".join([p for p in sub if p])


def _infer_lecture_from_upload(source_uri: str) -> str | None:
    key = _normalize_s3_key(source_uri)
    if not key:
        return None
    sub = _extract_upload_subpath(key, keep_filename=False)
    if not sub:
        return None
    lecture = _strip_media_dirs(sub)
    return lecture or None


def _strip_media_dirs(subpath: str) -> str:
    parts = [p for p in subpath.split("/") if p]
    cleaned = [p for p in parts if p not in MEDIA_DIR_NAMES]
    return "/".join(cleaned).strip("/")
