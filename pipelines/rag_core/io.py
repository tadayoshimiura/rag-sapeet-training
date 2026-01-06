"""RAG基盤の入出力ユーティリティ。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from .retrievers.fixed import RetrievalChunk


def render_context(chunks: Iterable[RetrievalChunk]) -> str:
    """
    チャンク群をCONTEXTテキストに整形する。

    Args:
        chunks (Iterable[RetrievalChunk]): コンテキスト候補。

    Returns:
        str: [source: ...] を含む文字列。

    Example:
        >>> render_context([])  # doctest: +SKIP
        ''
    """
    parts: List[str] = []
    for chunk in chunks:
        parts.append(f"[source: {chunk.source}]\n{chunk.content}\n")
    return "\n".join(parts).strip()


def save_answer(output_dir: str, answer: str, sources: List[RetrievalChunk], raw_response: dict) -> Path:
    """
    回答とメタデータをJSONで保存する。

    Args:
        output_dir (str): 保存先ディレクトリ。
        answer (str): LLMの回答本文。
        sources (List[RetrievalChunk]): 使用したチャンク一覧。
        raw_response (dict): LLMの生レスポンス。

    Returns:
        Path: 作成されたファイルパス。

    Example:
        >>> save_answer("outputs", "text", [], {})  # doctest: +SKIP
        PosixPath('outputs/answer.json')
    """
    runtime_dir = Path(output_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "answer": answer,
        "sources": [chunk.source for chunk in sources],
        "raw_response": raw_response,
    }
    output_path = runtime_dir / "answer.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return output_path
