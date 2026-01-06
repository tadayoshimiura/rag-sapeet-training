"""S3ベースのリトリーバ。"""
from __future__ import annotations

import json
import math
import os
import re
from typing import List, Optional, Sequence, Tuple

import boto3

from ..config import ActiveProviderContext
from .fixed import RetrievalChunk


def _get_profile_name() -> Optional[str]:
    """
    AWS_PROFILE環境変数を取得する。

    Returns:
        Optional[str]: 設定されていればプロファイル名。

    Example:
        >>> _get_profile_name()  # doctest: +SKIP
        'ReadWrite'
    """
    return os.getenv("AWS_PROFILE")


def _make_boto3_session(region_name: str) -> boto3.Session:
    """
    boto3.Sessionを作成する。AWS_PROFILEがあればそれを利用する。

    Args:
        region_name (str): 使用するリージョン。

    Returns:
        boto3.Session: S3やBedrockクライアントに共有するセッション。

    Example:
        >>> session = _make_boto3_session("ap-northeast-1")  # doctest: +SKIP
    """
    profile = _get_profile_name()
    if profile:
        return boto3.Session(profile_name=profile, region_name=region_name)
    return boto3.Session(region_name=region_name)


class S3Retriever:
    """Fetch documents from S3, chunk them, and return ranked snippets."""

    CHUNK_SIZE = 800

    def __init__(self, provider: ActiveProviderContext, strategy: str) -> None:
        """
        S3リトリーバーを初期化する。

        Args:
            provider (ActiveProviderContext): アクティブなAWSプロバイダ。

        Example:
            >>> retriever = S3Retriever(app_config)  # doctest: +SKIP
        """
        if provider.name != "aws":
            raise NotImplementedError("S3 retriever currently supports AWS only.")
        if not provider.storage:
            raise ValueError("Storage configuration is required for S3 retriever.")
        self._provider = provider
        self._region = provider.region
        self._bucket = provider.storage.s3_bucket
        self._prefix = provider.storage.s3_prefix
        self._session = _make_boto3_session(region_name=self._region)
        self._s3 = self._session.client("s3")
        self._chunks_cache: List[RetrievalChunk] | None = None
        self._chunk_vectors_cache: List[Tuple[RetrievalChunk, List[float]]] | None = None
        self._strategy = strategy
        self._embedder = _BedrockEmbedder(provider) if provider.embedding else None

    def fetch(self, question: str, top_k: int) -> List[RetrievalChunk]:
        """
        質問に関連するチャンクを上位top_k件返す。

        Args:
            question (str): ユーザーの質問。
            top_k (int): 取得するチャンク数。

        Returns:
            List[RetrievalChunk]: ランク済みチャンク。

        Example:
            >>> retriever.fetch("質問", 5)  # doctest: +SKIP
        """
        if top_k <= 0:
            return []
        chunks = self._load_chunks()
        if self._strategy == "vector":
            if not self._embedder:
                raise ValueError("retrieval.strategy='vector' requires models.embedding")
            ranked = self._rank_chunks_vector(question, chunks)
        else:
            ranked = self._rank_chunks_keyword(question, chunks)
        return ranked[:top_k]

    def _load_chunks(self) -> List[RetrievalChunk]:
        """
        S3からテキストを読み込みチャンク化する。

        Returns:
            List[RetrievalChunk]: キャッシュされたチャンク一覧。

        Example:
            >>> retriever._load_chunks()  # doctest: +SKIP
        """
        if self._chunks_cache is not None:
            return self._chunks_cache
        keys = self._list_object_keys()
        chunks: List[RetrievalChunk] = []
        for key in keys:
            text = self._read_object(key)
            chunks.extend(self._chunk_text(text, key))
        if not chunks:
            raise ValueError(
                f"No text chunks found under s3://{self._bucket}/{self._prefix}."
            )
        self._chunks_cache = chunks
        return chunks

    def _list_object_keys(self) -> List[str]:
        """
        対象プレフィックス配下のS3キーを列挙する。

        Returns:
            List[str]: 取得したキー。

        Raises:
            ValueError: データが存在しない場合。

        Example:
            >>> retriever._list_object_keys()  # doctest: +SKIP
        """
        paginator = self._s3.get_paginator("list_objects_v2")
        keys: List[str] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._prefix):
            for item in page.get("Contents", []):
                key = item.get("Key")
                if key:
                    keys.append(key)
        if not keys:
            raise ValueError(
                f"No objects found in s3://{self._bucket}/{self._prefix}."
            )
        return keys

    def _read_object(self, key: str) -> str:
        """
        S3オブジェクトを一件取得してデコードする。

        Args:
            key (str): オブジェクトキー。

        Returns:
            str: UTF-8文字列。

        Example:
            >>> retriever._read_object("kb_text/sample.txt")  # doctest: +SKIP
        """
        response = self._s3.get_object(Bucket=self._bucket, Key=key)
        body = response["Body"].read()
        return body.decode("utf-8", errors="ignore")

    def _chunk_text(self, text: str, key: str) -> List[RetrievalChunk]:
        """
        テキストを一定長のチャンクへ分割する。

        Args:
            text (str): 元の本文。
            key (str): 出典となったS3キー。

        Returns:
            List[RetrievalChunk]: チャンク化された結果。

        Example:
            >>> retriever._chunk_text("line1\\nline2", "kb_text/file.txt")  # doctest: +SKIP
        """
        normalized = text.replace("\r\n", "\n").strip()
        if not normalized:
            return []
        chunks: List[RetrievalChunk] = []
        start = 0
        idx = 1
        while start < len(normalized):
            end = min(len(normalized), start + self.CHUNK_SIZE)
            segment = normalized[start:end].strip()
            if segment:
                chunks.append(
                    RetrievalChunk(
                        source=f"{key}#chunk{idx}",
                        content=segment,
                    )
                )
            start = end
            idx += 1
        return chunks

    def _rank_chunks_keyword(self, question: str, chunks: Sequence[RetrievalChunk]) -> List[RetrievalChunk]:
        """
        キーワード一致数でチャンクをスコアリングする。

        Args:
            question (str): 質問文。
            chunks (Sequence[RetrievalChunk]): ランク対象。

        Returns:
            List[RetrievalChunk]: スコア順のチャンク。

        Example:
            >>> retriever._rank_chunks_keyword("質問", [])  # doctest: +SKIP
        """
        tokens = [tok for tok in re.split(r"\W+", question.lower()) if tok]
        scored: List[Tuple[int, int, RetrievalChunk]] = []
        for idx, chunk in enumerate(chunks):
            content_lower = chunk.content.lower()
            score = sum(1 for token in tokens if token and token in content_lower)
            scored.append((score, -idx, chunk))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [entry[2] for entry in scored]

    def _rank_chunks_vector(self, question: str, chunks: Sequence[RetrievalChunk]) -> List[RetrievalChunk]:
        """
        埋め込みベクトルの類似度でチャンクを並べ替える。

        Args:
            question (str): 質問文。
            chunks (Sequence[RetrievalChunk]): 評価対象。

        Returns:
            List[RetrievalChunk]: 類似度順リスト。

        Example:
            >>> retriever._rank_chunks_vector("質問", [])  # doctest: +SKIP
        """
        chunk_vectors = self._get_chunk_vectors(chunks)
        query_vector = self._embedder.embed_text(question) if question.strip() else None
        if query_vector is None:
            query_vector = self._embedder.embed_text("default query")
        scored: List[Tuple[float, int, RetrievalChunk]] = []
        for idx, (chunk, vector) in enumerate(chunk_vectors):
            score = self._cosine_similarity(query_vector, vector)
            scored.append((score, -idx, chunk))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [entry[2] for entry in scored]

    def _get_chunk_vectors(self, chunks: Sequence[RetrievalChunk]) -> List[Tuple[RetrievalChunk, List[float]]]:
        """
        チャンクの埋め込みを取得し、キャッシュを返す。

        Args:
            chunks (Sequence[RetrievalChunk]): 埋め込み対象。

        Returns:
            List[Tuple[RetrievalChunk, List[float]]]: チャンクとベクトルのペア。

        Example:
            >>> retriever._get_chunk_vectors([])  # doctest: +SKIP
        """
        if self._chunk_vectors_cache is not None and len(self._chunk_vectors_cache) == len(chunks):
            return self._chunk_vectors_cache
        if not self._embedder:
            raise ValueError("Embedding client not initialized")
        vectors: List[List[float]] = []
        for chunk in chunks:
            vectors.append(self._embedder.embed_text(chunk.content))
        self._chunk_vectors_cache = list(zip(chunks, vectors))
        return self._chunk_vectors_cache

    @staticmethod
    def _cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
        """
        2ベクトルのコサイン類似度を計算する。

        Args:
            vec_a (Sequence[float]): ベクトルA。
            vec_b (Sequence[float]): ベクトルB。

        Returns:
            float: 類似度値。

        Example:
            >>> S3Retriever._cosine_similarity([1, 0], [1, 0])
            1.0
        """
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a)) or 1e-9
        norm_b = math.sqrt(sum(b * b for b in vec_b)) or 1e-9
        return dot / (norm_a * norm_b)


class _BedrockEmbedder:
    """Minimal Bedrock embedding caller using boto3."""

    def __init__(self, provider: ActiveProviderContext) -> None:
        """
        Bedrock埋め込みクライアントを初期化する。

        Args:
            provider (ActiveProviderContext): 埋め込みモデル設定を含む。

        Raises:
            ValueError: 埋め込み設定が無い場合。

        Example:
            >>> embedder = _BedrockEmbedder(app_config)  # doctest: +SKIP
        """
        if provider.name != "aws":
            raise NotImplementedError("Embedding currently supports AWS only.")
        embedding_cfg = provider.embedding
        if embedding_cfg is None:
            raise ValueError("Embedding config is required")
        self._session = _make_boto3_session(region_name=provider.region)
        self._client = self._session.client("bedrock-runtime")
        self._model_id = embedding_cfg.model_id

    def embed_text(self, text: str) -> List[float]:
        """
        テキストを Bedrock でベクトル化する。

        Args:
            text (str): 埋め込み対象の本文。

        Returns:
            List[float]: 取得した埋め込みベクトル。

        Raises:
            ValueError: レスポンスに embedding が存在しない場合。

        Example:
            >>> embedder.embed_text("text")  # doctest: +SKIP
        """
        payload = {"inputText": text}
        response = self._client.invoke_model(
            modelId=self._model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(payload),
        )
        data = json.loads(response["body"].read())
        embedding = data.get("embedding")
        if embedding is None:
            raise ValueError("Bedrock embedding response missing 'embedding'")
        return embedding
