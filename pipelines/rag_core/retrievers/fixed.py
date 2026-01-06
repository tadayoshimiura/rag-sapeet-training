"""固定チャンクのリトリーバ。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class RetrievalChunk:
    source: str
    content: str


DEFAULT_CHUNKS: List[RetrievalChunk] = [
    RetrievalChunk(
        source="fixed#1",
        content=(
            "Amazon Bedrockはマネージドサービスとして複数のファウンデーションモデルを提供し、"
            "API経由でLLMやEmbeddingを利用できる。Bedrock RuntimeはAWS SDKからの呼び出しを"
            "サポートし、IAMロールでセキュアにアクセスできる。"
        ),
    ),
    RetrievalChunk(
        source="fixed#2",
        content=(
            "Step AではRetrieverを固定文字列にし、LLMへはContextとQuestionをプロンプトで渡す。"
            "回答と根拠(source)を返し、outputs/answer.jsonに保存する。"
        ),
    ),
]


class FixedRetriever:
    """Return a static set of chunks regardless of the question."""

    def __init__(self, chunks: Iterable[RetrievalChunk] | None = None) -> None:
        """
        固定チャンクを初期化する。

        Args:
            chunks (Iterable[RetrievalChunk] | None): 省略時はデフォルトチャンクを使用。

        Example:
            >>> FixedRetriever()  # doctest: +SKIP
        """
        self._chunks = list(chunks) if chunks is not None else list(DEFAULT_CHUNKS)

    def fetch(self, question: str, top_k: int) -> List[RetrievalChunk]:
        """
        固定チャンクのうち上位 top_k 件を返す。

        Args:
            question (str): 無視される質問文。
            top_k (int): 返却するチャンク数。

        Returns:
            List[RetrievalChunk]: コンテキストとして使うチャンク群。

        Example:
            >>> FixedRetriever().fetch("Q", 1)
            [RetrievalChunk(...)]
        """
        del question  # question is unused for the fixed retriever
        return self._chunks[:top_k]
