"""Markdownからcontextsを構築する。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from shared.front_matter import parse_md_meta, split_front_matter


@dataclass(frozen=True)
class ContextChunk:
    """{contexts} の1チャンク。"""

    chunk_id: str
    text: str
    source: Dict[str, Any]


def build_contexts_from_markdown_dir(
    root_dir: str,
    max_chars_per_chunk: int = 1200,
    include_source: bool = True,
    max_files: Optional[int] = None,
    max_chunks: Optional[int] = None,
    max_total_chars: Optional[int] = None,
) -> List[ContextChunk]:
    """ローカルのMarkdown群から {contexts} を構築する。

    生成系LLMに渡す {contexts} が肥大化しやすいので、運用上は
    `max_files` / `max_chunks` / `max_total_chars` を使って上限を設ける。
    """
    root = Path(root_dir)
    md_paths = sorted(root.rglob("*.md"))
    if max_files is not None:
        md_paths = md_paths[: max(0, int(max_files))]
    return build_contexts_from_markdown_files(
        md_paths,
        max_chars_per_chunk=max_chars_per_chunk,
        include_source=include_source,
        max_chunks=max_chunks,
        max_total_chars=max_total_chars,
    )


def build_contexts_from_markdown_files(
    md_files: Iterable[str | Path],
    max_chars_per_chunk: int = 1200,
    include_source: bool = True,
    max_chunks: Optional[int] = None,
    max_total_chars: Optional[int] = None,
) -> List[ContextChunk]:
    """指定したMarkdownファイル群から {contexts} を構築する。"""
    paths = [Path(p) for p in md_files]
    chunks: List[ContextChunk] = []
    for p in paths:
        text = p.read_text(encoding="utf-8", errors="replace")
        meta = parse_md_meta(text)
        _, body = split_front_matter(text)
        src = {
            "source_path": meta.source_path or str(p),
            "source_type": meta.source_type or "unknown",
            "course_id": meta.course_id,
            "lecture_id": meta.lecture_id,
        }
        parts = _split_markdown_to_units(body)
        for idx, unit in enumerate(_pack_units(parts, max_chars=max_chars_per_chunk), start=1):
            chunk_id = _make_chunk_id(meta.source_path or str(p), idx)
            chunks.append(ContextChunk(chunk_id=chunk_id, text=unit, source=src if include_source else {}))
            if max_chunks is not None and len(chunks) >= int(max_chunks):
                return _trim_total_chars(chunks, max_total_chars)
            if max_total_chars is not None:
                trimmed = _trim_total_chars(chunks, max_total_chars)
                if len(trimmed) != len(chunks):
                    return trimmed
    return chunks


def to_contexts_payload(chunks: List[ContextChunk]) -> List[dict]:
    """Dify等の {contexts} と同様の配列へ変換する。"""
    out = []
    for c in chunks:
        item = {"chunk_id": c.chunk_id, "text": c.text}
        if c.source:
            item["source"] = c.source
        out.append(item)
    return out


def _split_markdown_to_units(body: str) -> List[str]:
    lines = body.replace("\r\n", "\n").splitlines()
    units: List[str] = []
    buf: List[str] = []
    for line in lines:
        if line.startswith("#"):
            if buf:
                units.append("\n".join(buf).strip())
                buf = []
            units.append(line.strip())
            continue
        if not line.strip():
            if buf:
                units.append("\n".join(buf).strip())
                buf = []
            continue
        buf.append(line.rstrip())
    if buf:
        units.append("\n".join(buf).strip())
    return [u for u in units if u]


def _pack_units(units: List[str], max_chars: int) -> List[str]:
    out: List[str] = []
    buf: List[str] = []
    n = 0
    for u in units:
        if len(u) > max_chars:
            if buf:
                out.append("\n\n".join(buf).strip())
                buf = []
                n = 0
            out.extend([u[i : i + max_chars] for i in range(0, len(u), max_chars)])
            continue
        add = len(u) + (2 if buf else 0)
        if n + add > max_chars:
            out.append("\n\n".join(buf).strip())
            buf = [u]
            n = len(u)
        else:
            buf.append(u)
            n += add
    if buf:
        out.append("\n\n".join(buf).strip())
    return out


def _make_chunk_id(source_path: str, idx: int) -> str:
    h = hashlib.sha1(source_path.encode("utf-8")).hexdigest()[:10]
    return f"c_{h}_{idx:04d}"


def _trim_total_chars(chunks: List[ContextChunk], max_total_chars: Optional[int]) -> List[ContextChunk]:
    """contextsの合計文字数が上限を超える場合に末尾を削る。"""
    if max_total_chars is None:
        return chunks
    limit = max(0, int(max_total_chars))
    total = 0
    out: List[ContextChunk] = []
    for c in chunks:
        total += len(c.text)
        if total > limit:
            break
        out.append(c)
    return out
