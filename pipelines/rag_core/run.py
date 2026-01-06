"""RAG基盤の実行入口。"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Protocol

from langchain_core.runnables import RunnableSequence

from .config import AppConfig, ActiveProviderContext, RetrievalConfig, load_config, resolve_active_provider
from .io import render_context, save_answer
from .providers.bedrock import BedrockLLM, LangChainBedrockLLM
from .prompts import PromptProfileSelector, PromptSettings
from .retrievers import FixedRetriever, RetrievalChunk, S3Retriever


class Retriever(Protocol):
    def fetch(self, question: str, top_k: int) -> List[RetrievalChunk]:
        ...


RetrieverFactory = Callable[[ActiveProviderContext, RetrievalConfig], Retriever]

RETRIEVER_BUILDERS: dict[str, RetrieverFactory] = {
    "fixed": lambda _provider, _retrieval: FixedRetriever(),
    "s3": lambda provider, retrieval: S3Retriever(provider, retrieval.strategy),
}


@dataclass
class RuntimeSettings:
    """
    RAGを動かす際の主要な設定値だけをまとめたオブジェクト。
    ここを編集すれば挙動の多くを調整できる。
    """

    provider_name: str
    region: str
    llm_identifier: str
    llm_temperature: float
    llm_max_tokens: int
    retrieval_type: str
    retrieval_strategy: str
    retrieval_top_k: int
    storage_bucket: str
    storage_prefix: str
    prompt_system: str
    prompt_user: str
    prompt_source: str
    prompt_profile_name: str | None = None
    memory_enabled: bool = False
    memory_key: str = ""
    memory_history_window: int = 10
    output_dir: str = "outputs"

    @classmethod
    def from_config(
        cls,
        config: AppConfig,
        prompt_settings: PromptSettings,
        provider: ActiveProviderContext,
    ) -> "RuntimeSettings":
        """
        AppConfigと選択済みプロンプト/プロバイダ情報からRuntimeSettingsを構築する。

        Args:
            config (AppConfig): JSONから読み込んだアプリ設定。
            prompt_settings (PromptSettings): プロンプト選択ロジックが返す設定。
            provider (ActiveProviderContext): 現在アクティブなクラウドの接続情報。

        Returns:
            RuntimeSettings: CLI実行時に参照するまとめ済み設定。

        Example:
            >>> cfg = load_config("configs/rag_runtime_dev.json")  # doctest: +SKIP
            >>> provider = resolve_active_provider(cfg)  # doctest: +SKIP
            >>> RuntimeSettings.from_config(cfg, PromptSettings(), provider)  # doctest: +SKIP
        """
        prompt_source = "config override" if (config.prompts.system or config.prompts.user) else "default"
        llm_identifier = provider.llm.inference_profile_arn or provider.llm.model_id or "(not set)"
        if not provider.storage:
            raise ValueError("Active provider missing storage configuration.")
        return cls(
            provider_name=provider.name,
            region=provider.region,
            llm_identifier=llm_identifier,
            llm_temperature=provider.llm.temperature,
            llm_max_tokens=provider.llm.max_tokens,
            retrieval_type=config.retrieval.type,
            retrieval_strategy=config.retrieval.strategy,
            retrieval_top_k=config.retrieval.top_k,
            storage_bucket=provider.storage.s3_bucket,
            storage_prefix=provider.storage.s3_prefix,
            prompt_system=prompt_settings.system,
            prompt_user=prompt_settings.user,
            prompt_source=prompt_source,
            prompt_profile_name=prompt_settings.profile_name,
            memory_enabled=config.memory.type == "buffer",
            memory_key=config.memory.memory_key,
            output_dir=config.runtime.output_dir,
        )


def _build_retriever(provider: ActiveProviderContext, retrieval: RetrievalConfig) -> Retriever:
    """
    設定に応じたリトリーバーを生成する。

    Args:
        provider (ActiveProviderContext): アクティブなクラウド設定。
        retrieval (RetrievalConfig): リトリーバー設定。

    Returns:
        Retriever: 固定もしくはS3ベースのリトリーバー。

    Raises:
        ValueError: 未対応のタイプが指定された場合。

    Example:
        >>> _build_retriever(config)  # doctest: +SKIP
    """
    retriever_type = retrieval.type
    try:
        builder = RETRIEVER_BUILDERS[retriever_type]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported retrieval.type '{retriever_type}'") from exc
    return builder(provider, retrieval)


def _print_config_summary(settings: RuntimeSettings) -> None:
    """
    現在の設定を把握しやすいよう、主要項目を表示する。
    """
    preview = settings.prompt_system.strip().splitlines()[0]
    print("=== RAG Configuration ===")
    print(f"- Provider          : {settings.provider_name} ({settings.region})")
    print(f"- LLM identifier    : {settings.llm_identifier}")
    print(f"- LLM temperature   : {settings.llm_temperature}")
    print(f"- Retrieval type    : {settings.retrieval_type} (strategy={settings.retrieval_strategy}, top_k={settings.retrieval_top_k})")
    print(f"- Storage source    : {settings.storage_bucket}/{settings.storage_prefix}")
    print(f"- Prompt source     : {settings.prompt_source}")
    if settings.prompt_profile_name:
        print(f"- Active profile    : {settings.prompt_profile_name}")
    print(f"- Memory enabled    : {settings.memory_enabled} (key={settings.memory_key})")
    print(f"- System prompt head: {preview[:80]}")
    print("========================\n")


class RAGApplication:
    """
    RAG全体のコンポーネントを束ねるオーケストレーター。

    Args:
        retriever (Retriever): コンテキスト取得ロジック。
        chain (RunnableSequence): LangChain Runnableで構成したLLMチェーン。
        llm_adapter (LangChainBedrockLLM): 直近レスポンスを保持するLLMラッパー。

    Example:
        >>> app = RAGApplication.from_config(load_config("configs/rag_runtime_dev.json"))  # doctest: +SKIP
    """

    def __init__(
        self,
        settings: RuntimeSettings,
        retriever: Retriever,
        chain: RunnableSequence,
        llm_adapter: LangChainBedrockLLM,
    ) -> None:
        self._settings = settings
        self._retriever = retriever
        self._chain = chain
        self._llm_adapter = llm_adapter
        self._history: List[str] = []

    def answer(self, question: str) -> None:
        """
        質問に対してRAG処理を実行し、出力を保存・表示する。

        Args:
            question (str): ユーザー質問。
        """
        chunks: List[RetrievalChunk] = self._retriever.fetch(
            question=question,
            top_k=self._settings.retrieval_top_k,
        )
        context = render_context(chunks) or "(CONTEXTなし)"
        inputs = {"context": context, "question": question.strip()}
        if self._settings.memory_enabled:
            inputs["history"] = "\n".join(self._history[-self._settings.memory_history_window :]) if self._history else "(no history)"
        raw_chain_output = self._chain.invoke(inputs)
        if isinstance(raw_chain_output, str):
            answer_text = raw_chain_output.strip()
        elif isinstance(raw_chain_output, dict):
            answer_text = str(raw_chain_output.get("text", "")).strip()
        else:
            answer_text = str(raw_chain_output).strip()
        if self._settings.memory_enabled:
            self._history.append(f"Q: {question.strip()}\nA: {answer_text}")
        latest = self._llm_adapter.latest_response
        raw_response = latest.raw if latest else {}
        output_path = save_answer(
            output_dir=self._settings.output_dir,
            answer=answer_text,
            sources=chunks,
            raw_response=raw_response,
        )
        self._print_result(answer_text, chunks, output_path)

    def _print_result(self, answer_text: str, chunks: List[RetrievalChunk], output_path: Path) -> None:
        """
        CLIで結果を見やすく表示する。

        Args:
            answer_text (str): LLMの回答。
            chunks (List[RetrievalChunk]): 利用したチャンク。
            output_path (Path): 保存先ファイルパス。
        """
        print("=== Answer ===")
        print(answer_text)
        print("\n=== Sources ===")
        for chunk in chunks:
            print(f"- {chunk.source}")
        print(f"\nSaved to {output_path}")


def run(question: str, config_path: str) -> None:
    """
    CLIから呼び出される実行関数。

    Args:
        question (str): ユーザー質問。
        config_path (str): JSON設定ファイルパス。

    Example:
        >>> run("質問", "configs/rag_runtime_dev.json")  # doctest: +SKIP
    """
    config = load_config(config_path)
    provider_ctx = resolve_active_provider(config)
    backend = BedrockLLM(provider_ctx)
    prompt_settings = _select_prompt_settings(question, config, backend)
    runtime_settings = RuntimeSettings.from_config(config, prompt_settings, provider_ctx)
    _print_config_summary(runtime_settings)

    app = _build_application(
        settings=runtime_settings,
        config=config,
        provider=provider_ctx,
        backend=backend,
        prompt_settings=prompt_settings,
    )
    app.answer(question)


def _select_prompt_settings(
    question: str,
    config: AppConfig,
    backend: BedrockLLM,
) -> PromptSettings:
    """
    質問内容に応じて最適なSystem Promptを選択し、PromptSettingsを返す。
    """
    selector = PromptProfileSelector(backend)
    selected_profile = selector.select(
        question=question,
        profiles=config.prompts.profiles,
        variables=config.prompts.variables,
    )
    system_override = selected_profile.system if selected_profile else None
    profile_name = selected_profile.name if selected_profile else None
    return PromptSettings.from_config(
        config.prompts,
        system_override=system_override,
        profile_name=profile_name,
    )


def _build_application(
    settings: RuntimeSettings,
    config: AppConfig,
    provider: ActiveProviderContext,
    backend: BedrockLLM,
    prompt_settings: PromptSettings,
) -> RAGApplication:
    """
    RuntimeSettingsを基にRetriever/LLM/チェーンを構築し、RAGApplicationを返す。
    """
    retriever = _build_retriever(provider, config.retrieval)
    llm_adapter = LangChainBedrockLLM(backend=backend, system_prompt=settings.prompt_system)
    prompt_template = prompt_settings.build_template(include_history=settings.memory_enabled)
    chain = prompt_template | llm_adapter
    return RAGApplication(
        settings=settings,
        retriever=retriever,
        chain=chain,
        llm_adapter=llm_adapter,
    )


def main(argv: List[str] | None = None) -> None:
    """
    エントリーポイント。引数をパースして run を呼ぶ。

    Args:
        argv (List[str] | None): テスト用の引数リスト。

    Example:
        >>> main(["--question", "Q"])  # doctest: +SKIP
    """
    os.environ.setdefault("AWS_SDK_LOAD_CONFIG", "1")
    parser = argparse.ArgumentParser(description="Run the minimal AWS Bedrock RAG pipeline.")
    parser.add_argument("--question", required=True, help="Question to send through the RAG pipeline")
    parser.add_argument(
        "--config",
        default="configs/rag_runtime_dev.json",
        help="Path to the JSON config file",
    )
    args = parser.parse_args(argv)

    run(question=args.question, config_path=args.config)


if __name__ == "__main__":  # pragma: no cover
    main()
