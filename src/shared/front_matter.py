"""Markdownのフロントマター解析。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import yaml


@dataclass(frozen=True)
class MdMeta:
    """Markdown先頭のメタ情報（YAMLフロントマター）。"""

    course_id: str | None
    lecture_id: str | None
    category: str | None
    source_path: str | None
    source_type: str | None


def split_front_matter(text: str) -> Tuple[Optional[dict], str]:
    """YAMLフロントマターがあれば分離する。無ければ(None, text)。"""
    s = text.lstrip()
    if not s.startswith("---\n"):
        return None, text
    end = s.find("\n---", 4)
    if end == -1:
        return None, text
    header = s[4:end].strip("\n")
    body = s[end + 4 :].lstrip("\n")
    try:
        meta = yaml.safe_load(header) or {}
        if not isinstance(meta, dict):
            return None, text
        return meta, body
    except Exception:
        return None, text


def parse_md_meta(text: str) -> MdMeta:
    """Markdown本文からメタ情報を抽出する。"""
    meta, _ = split_front_matter(text)
    if not meta:
        return MdMeta(course_id=None, lecture_id=None, category=None, source_path=None, source_type=None)
    return MdMeta(
        course_id=_as_str(meta.get("course_id")),
        lecture_id=_as_str(meta.get("lecture_id")),
        category=_as_str(meta.get("category")),
        source_path=_as_str(meta.get("source_path")),
        source_type=_as_str(meta.get("source_type")),
    )


def _as_str(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None
