"""Manage the configuration of various retrievers.

This module provides functionality to create and manage retrievers for different
vector store backends, specifically Elasticsearch, Pinecone, and MongoDB.
"""

import asyncio
import os
from contextlib import contextmanager
from typing import Generator

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableConfig

from shared.configuration import BaseConfiguration

## Encoder constructors


def make_text_encoder(model: str) -> Embeddings:
    """Connect to the configured text encoder."""
    provider, model = model.split("/", maxsplit=1)
    match provider:
        case "openai":
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(model=model)
        case "cohere":
            from langchain_cohere import CohereEmbeddings

            return CohereEmbeddings(model=model)  # type: ignore
        case "bedrock":
            try:
                from langchain_aws import BedrockEmbeddings
            except ImportError as exc:
                raise ImportError(
                    "Bedrock Embeddings を使うには langchain-aws が必要です。"
                ) from exc

            region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
            if not region:
                raise ValueError("AWS_REGION が未設定です")
            return BedrockEmbeddings(model_id=model, region_name=region)
        case _:
            raise ValueError(f"Unsupported embedding provider: {provider}")


## Retriever constructors


@contextmanager
def make_elastic_retriever(
    configuration: BaseConfiguration, embedding_model: Embeddings
) -> Generator[BaseRetriever, None, None]:
    """Configure this agent to connect to a specific elastic index."""
    from langchain_elasticsearch import ElasticsearchStore

    connection_options = {}
    if configuration.retriever_provider == "elastic-local":
        connection_options = {
            "es_user": os.environ["ELASTICSEARCH_USER"],
            "es_password": os.environ["ELASTICSEARCH_PASSWORD"],
        }

    else:
        connection_options = {"es_api_key": os.environ["ELASTICSEARCH_API_KEY"]}

    vstore = ElasticsearchStore(
        **connection_options,  # type: ignore
        es_url=os.environ["ELASTICSEARCH_URL"],
        index_name="langchain_index",
        embedding=embedding_model,
    )

    yield vstore.as_retriever(search_kwargs=configuration.search_kwargs)


@contextmanager
def make_pinecone_retriever(
    configuration: BaseConfiguration, embedding_model: Embeddings
) -> Generator[BaseRetriever, None, None]:
    """Configure this agent to connect to a specific pinecone index."""
    from langchain_pinecone import PineconeVectorStore

    vstore = PineconeVectorStore.from_existing_index(
        os.environ["PINECONE_INDEX_NAME"], embedding=embedding_model
    )
    yield vstore.as_retriever(search_kwargs=configuration.search_kwargs)


@contextmanager
def make_mongodb_retriever(
    configuration: BaseConfiguration, embedding_model: Embeddings
) -> Generator[BaseRetriever, None, None]:
    """Configure this agent to connect to a specific MongoDB Atlas index & namespaces."""
    from langchain_mongodb.vectorstores import MongoDBAtlasVectorSearch

    vstore = MongoDBAtlasVectorSearch.from_connection_string(
        os.environ["MONGODB_URI"],
        namespace="langgraph_retrieval_agent.default",
        embedding=embedding_model,
    )
    yield vstore.as_retriever(search_kwargs=configuration.search_kwargs)


def _build_opensearch_auth():
    """OpenSearch の認証情報を組み立てる。

    Returns:
        object | tuple | None: IAM署名オブジェクト / ベーシック認証タプル / None のいずれか。

    Examples:
        >>> _build_opensearch_auth()  # doctest: +SKIP
        <AWSV4SignerAuth ...>
    """
    use_iam = os.getenv("OPENSEARCH_USE_IAM", "true").lower() == "true"
    if use_iam:
        from opensearchpy import AWSV4SignerAuth
        import boto3

        region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
        if not region:
            raise ValueError("AWS_REGION が未設定です")
        service = os.getenv("OPENSEARCH_SERVICE", "aoss")
        credentials = boto3.Session().get_credentials()
        if not credentials:
            raise ValueError("AWS 認証情報が取得できません")
        return AWSV4SignerAuth(credentials, region, service)

    user = os.getenv("OPENSEARCH_USER")
    password = os.getenv("OPENSEARCH_PASSWORD")
    if user and password:
        return (user, password)
    return None


@contextmanager
def make_opensearch_retriever(
    configuration: BaseConfiguration, embedding_model: Embeddings
) -> Generator[BaseRetriever, None, None]:
    """OpenSearch のリトリーバを構成する。

    Args:
        configuration (BaseConfiguration): 検索設定（search_kwargs など）。
        embedding_model (Embeddings): 埋め込みモデル。

    Returns:
        Generator[BaseRetriever, None, None]: リトリーバのコンテキスト。

    Examples:
        >>> # OPENSEARCH_URL を設定して実行
        >>> # with make_opensearch_retriever(cfg, emb) as r: ...
        >>> pass
    """
    from langchain_community.vectorstores import OpenSearchVectorSearch

    opensearch_url = os.environ["OPENSEARCH_URL"]
    index_name = os.getenv("OPENSEARCH_INDEX", "langchain_index")
    http_auth = _build_opensearch_auth()

    vstore = OpenSearchVectorSearch(
        opensearch_url=opensearch_url,
        index_name=index_name,
        embedding_function=embedding_model,
        http_auth=http_auth,
    )
    yield vstore.as_retriever(search_kwargs=configuration.search_kwargs)


@contextmanager
def make_bedrock_kb_retriever(
    configuration: BaseConfiguration,
) -> Generator[BaseRetriever, None, None]:
    """Bedrock Knowledge Bases 用のリトリーバを構成する。"""
    import boto3

    kb_id = os.getenv("BEDROCK_KB_ID") or os.getenv("KB_ID")
    if not kb_id:
        raise ValueError("BEDROCK_KB_ID もしくは KB_ID が未設定です")

    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        raise ValueError("AWS_REGION が未設定です")

    search_kwargs = configuration.search_kwargs or {}
    top_k = int(
        search_kwargs.get("k")
        or search_kwargs.get("top_k")
        or search_kwargs.get("number_of_results")
        or 4
    )
    vector_search_config: dict[str, object] = {"numberOfResults": top_k}
    if "filter" in search_kwargs:
        vector_search_config["filter"] = search_kwargs["filter"]

    retrieval_config = {"vectorSearchConfiguration": vector_search_config}

    class BedrockKnowledgeBaseRetriever(BaseRetriever):
        """Bedrock Knowledge Bases の Retrieve API を使う最小リトリーバ。"""

        def __init__(self) -> None:
            super().__init__()
            self._client = boto3.client("bedrock-agent-runtime", region_name=region)

        def _get_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
            response = self._client.retrieve(
                knowledgeBaseId=kb_id,
                retrievalQuery={"text": query},
                retrievalConfiguration=retrieval_config,
            )
            return self._format_results(response)

        async def _aget_relevant_documents(
            self, query: str, *, run_manager=None
        ) -> list[Document]:
            response = await asyncio.to_thread(
                self._client.retrieve,
                knowledgeBaseId=kb_id,
                retrievalQuery={"text": query},
                retrievalConfiguration=retrieval_config,
            )
            return self._format_results(response)

        def _format_results(self, response: dict) -> list[Document]:
            results = response.get("retrievalResults", []) or []
            documents: list[Document] = []
            for result in results:
                content = result.get("content", {}).get("text", "")
                if not content:
                    continue
                metadata: dict[str, object] = {}
                score = result.get("score") or result.get("relevanceScore")
                if score is not None:
                    metadata["score"] = score
                location = result.get("location") or {}
                source_uri = (
                    location.get("s3Location", {}) or {}
                ).get("uri") or (location.get("webLocation", {}) or {}).get("url")
                if source_uri:
                    metadata["source"] = source_uri
                if "metadata" in result:
                    metadata["metadata"] = result["metadata"]
                documents.append(Document(page_content=content, metadata=metadata))
            return documents

        async def aadd_documents(self, *args, **kwargs) -> None:  # type: ignore[override]
            raise ValueError(
                "Bedrock Knowledge Bases では index_graph による追加は使えません。"
            )

    yield BedrockKnowledgeBaseRetriever()


@contextmanager
def make_retriever(
    config: RunnableConfig,
) -> Generator[BaseRetriever, None, None]:
    """Create a retriever for the agent, based on the current configuration."""
    configuration = BaseConfiguration.from_runnable_config(config)
    match configuration.retriever_provider:
        case "bedrock-kb":
            with make_bedrock_kb_retriever(configuration) as retriever:
                yield retriever
            return

    embedding_model = make_text_encoder(configuration.embedding_model)
    match configuration.retriever_provider:
        case "elastic" | "elastic-local":
            with make_elastic_retriever(configuration, embedding_model) as retriever:
                yield retriever

        case "pinecone":
            with make_pinecone_retriever(configuration, embedding_model) as retriever:
                yield retriever

        case "mongodb":
            with make_mongodb_retriever(configuration, embedding_model) as retriever:
                yield retriever

        case "opensearch":
            with make_opensearch_retriever(configuration, embedding_model) as retriever:
                yield retriever

        case _:
            raise ValueError(
                "Unrecognized retriever_provider in configuration. "
                f"Expected one of: {', '.join(BaseConfiguration.__annotations__['retriever_provider'].__args__)}\n"
                f"Got: {configuration.retriever_provider}"
            )
