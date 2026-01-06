"""RAG基盤の設定定義。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class LLMConfig:
    model_id: str | None = None
    inference_profile_arn: str | None = None
    max_tokens: int = 800
    temperature: float = 0.2


@dataclass
class EmbeddingConfig:
    model_id: str


@dataclass
class ModelsConfig:
    llm: LLMConfig
    embedding: EmbeddingConfig | None = None


@dataclass
class PromptProfile:
    name: str
    description: str
    system: str


@dataclass
class PromptConfig:
    system: str | None = None
    user: str | None = None
    variables: Dict[str, str] = field(default_factory=dict)
    profiles: List[PromptProfile] = field(default_factory=list)


@dataclass
class MemoryConfig:
    type: str = "none"
    memory_key: str = "history"
    input_key: str = "question"


@dataclass
class RetrievalConfig:
    type: str = "fixed"
    top_k: int = 5
    strategy: str = "keyword"


@dataclass
class StorageConfig:
    s3_bucket: str
    s3_prefix: str


@dataclass
class RuntimeConfig:
    output_dir: str = "outputs"


@dataclass
class AWSProviderConfig:
    region: str
    llm: LLMConfig
    embedding: EmbeddingConfig | None = None
    storage: StorageConfig | None = None


@dataclass
class AzureProviderConfig:
    endpoint: str | None = None
    llm_deployment: str | None = None
    embedding_deployment: str | None = None
    storage_account: str | None = None
    container: str | None = None


@dataclass
class GCPProviderConfig:
    project: str | None = None
    location: str | None = None
    llm_model: str | None = None
    embedding_model: str | None = None
    bucket: str | None = None
    prefix: str | None = None


@dataclass
class ProvidersConfig:
    active: str = "aws"
    aws: AWSProviderConfig | None = None
    azure: AzureProviderConfig | None = None
    gcp: GCPProviderConfig | None = None


@dataclass
class AppConfig:
    providers: ProvidersConfig
    retrieval: RetrievalConfig
    prompts: PromptConfig
    memory: MemoryConfig
    runtime: RuntimeConfig


@dataclass
class ActiveProviderContext:
    name: str
    region: str
    llm: LLMConfig
    embedding: EmbeddingConfig | None
    storage: StorageConfig


def _load_json(path: Path) -> Dict[str, Any]:
    """
    JSONファイルを読み込む単純なヘルパー。

    Args:
        path (Path): 読み込みたい設定ファイルのパス。

    Returns:
        Dict[str, Any]: JSONを辞書として返す。

    Example:
        >>> _load_json(Path("configs/rag_runtime_dev.json"))  # doctest: +SKIP
        {"aws": {"region": "ap-northeast-1"}, ...}
    """
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_config(path: str | Path) -> AppConfig:
    """
    JSON設定ファイルを読み込み、AppConfigツリーへ変換する。
    """
    config_path = Path(path)
    payload = _load_json(config_path)

    providers = _parse_providers(payload)
    retrieval = RetrievalConfig(**payload.get("retrieval", {}))
    prompts_payload = payload.get("prompts", {})
    profiles_payload = prompts_payload.get("profiles", [])
    prompt_profiles = [PromptProfile(**profile) for profile in profiles_payload]
    prompts = PromptConfig(
        system=prompts_payload.get("system"),
        user=prompts_payload.get("user"),
        variables=prompts_payload.get("variables", {}),
        profiles=prompt_profiles,
    )
    memory = MemoryConfig(**payload.get("memory", {}))
    runtime = RuntimeConfig(**payload.get("runtime", {}))

    return AppConfig(
        providers=providers,
        retrieval=retrieval,
        prompts=prompts,
        memory=memory,
        runtime=runtime,
    )


def _parse_providers(payload: Dict[str, Any]) -> ProvidersConfig:
    providers_payload = payload.get("providers")
    if providers_payload:
        return _build_providers(providers_payload)
    return _parse_legacy_providers(payload)


def _build_providers(providers_payload: Dict[str, Any]) -> ProvidersConfig:
    active = providers_payload.get("active", "aws")

    aws_config = None
    aws_payload = providers_payload.get("aws")
    if aws_payload:
        llm_payload = aws_payload.get("llm", {})
        embedding_payload = aws_payload.get("embedding")
        storage_payload = aws_payload.get("storage")
        llm_cfg = LLMConfig(**llm_payload)
        embedding_cfg = EmbeddingConfig(**embedding_payload) if embedding_payload else None
        storage_cfg = StorageConfig(**storage_payload) if storage_payload else None
        aws_config = AWSProviderConfig(
            region=aws_payload["region"],
            llm=llm_cfg,
            embedding=embedding_cfg,
            storage=storage_cfg,
        )

    azure_payload = providers_payload.get("azure")
    azure_config = AzureProviderConfig(**azure_payload) if azure_payload else None

    gcp_payload = providers_payload.get("gcp")
    gcp_config = GCPProviderConfig(**gcp_payload) if gcp_payload else None

    return ProvidersConfig(
        active=active,
        aws=aws_config,
        azure=azure_config,
        gcp=gcp_config,
    )


def _parse_legacy_providers(payload: Dict[str, Any]) -> ProvidersConfig:
    aws_payload = payload.get("aws")
    models_payload = payload.get("models")
    storage_payload = payload.get("storage")
    if not (aws_payload and models_payload and storage_payload):
        raise ValueError("Missing provider configuration. Please specify providers block.")

    llm_cfg = LLMConfig(**models_payload["llm"])
    embedding_payload = models_payload.get("embedding")
    embedding_cfg = EmbeddingConfig(**embedding_payload) if embedding_payload else None
    storage_cfg = StorageConfig(**storage_payload)
    aws_config = AWSProviderConfig(
        region=aws_payload["region"],
        llm=llm_cfg,
        embedding=embedding_cfg,
        storage=storage_cfg,
    )
    return ProvidersConfig(active="aws", aws=aws_config)


def resolve_active_provider(config: AppConfig) -> ActiveProviderContext:
    """
    現在アクティブなクラウドプロバイダ設定を返す。未対応の場合は例外。
    """
    name = config.providers.active.lower()
    if name == "aws":
        if not config.providers.aws or not config.providers.aws.storage:
            raise ValueError("AWS provider configuration is incomplete.")
        aws = config.providers.aws
        return ActiveProviderContext(
            name="aws",
            region=aws.region,
            llm=aws.llm,
            embedding=aws.embedding,
            storage=aws.storage,
        )
    raise NotImplementedError(f"Provider '{name}' is not supported yet.")
