#!/usr/bin/env python3
"""knowledge_md を読み込んで index_graph を実行する。"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Iterable, List

from langchain_core.documents import Document

from index_graph.graph import graph
from shared.front_matter import parse_md_meta, split_front_matter


def _load_config(path: str) -> dict:
    """設定JSONを読み込む。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _iter_markdown_files(root: Path, max_files: int | None) -> List[Path]:
    md_paths = sorted(root.rglob("*.md"))
    if max_files is not None:
        md_paths = md_paths[: max(0, int(max_files))]
    return md_paths


def _build_documents(md_files: Iterable[Path], course_id: str, lecture_id: str) -> list[Document]:
    """MarkdownからDocument配列を作る。"""
    docs: list[Document] = []
    for p in md_files:
        text = p.read_text(encoding="utf-8", errors="replace")
        meta = parse_md_meta(text)
        _, body = split_front_matter(text)
        content = body.strip() or text.strip()
        metadata = {
            "source_path": meta.source_path or str(p),
            "source_type": meta.source_type or "unknown",
            "course_id": meta.course_id or course_id,
            "lecture_id": meta.lecture_id or lecture_id,
            "source_md": p.name,
        }
        docs.append(Document(page_content=content, metadata=metadata))
    return docs


def main() -> None:
    parser = argparse.ArgumentParser(description="knowledge_md を index_graph に投入する")
    parser.add_argument("--kb-dir", required=True, help="knowledge_md/v1/<lecture_id> のローカルパス")
    parser.add_argument("--course-id", required=True, help="course_id=... 形式")
    parser.add_argument("--lecture-id", default=None, help="lecture_id（未指定ならフォルダ名）")
    parser.add_argument("--config", default="configs/opensearch_defaults.json", help="設定JSON")
    parser.add_argument("--max-md-files", type=int, default=None, help="読むMarkdown数の上限")
    parser.add_argument("--dry-run", action="store_true", help="投入せず件数だけ確認する")
    args = parser.parse_args()

    kb_dir = Path(args.kb_dir)
    if not kb_dir.exists():
        raise SystemExit(f"kb-dir が見つかりません: {kb_dir}")

    lecture_id = args.lecture_id or kb_dir.name
    config_data = _load_config(args.config)
    md_files = _iter_markdown_files(kb_dir, args.max_md_files)
    docs = _build_documents(md_files, args.course_id, lecture_id)

    if args.dry_run:
        print(f"docs={len(docs)} lecture_id={lecture_id}")
        return

    asyncio.run(graph.ainvoke({"docs": docs}, config={"configurable": config_data}))
    print(f"indexed docs={len(docs)} lecture_id={lecture_id}")


if __name__ == "__main__":
    main()
