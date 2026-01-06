"""Bedrock用プロバイダ実装。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.llms import LLM
from pydantic import PrivateAttr

import boto3

from ..config import ActiveProviderContext


@dataclass
class BedrockResponse:
    text: str
    raw: Dict[str, object]


class BedrockLLM:
    """Invoke an AWS Bedrock model using Anthropic's message format."""

    ANTHROPIC_VERSION = "bedrock-2023-05-31"

    def __init__(self, provider: ActiveProviderContext) -> None:
        """
        Bedrockクライアントを初期化する。

        Args:
            provider (ActiveProviderContext): アクティブなAWSプロバイダ設定。

        Example:
            >>> llm = BedrockLLM(app_config)  # doctest: +SKIP
        """
        self._model_cfg = provider.llm
        self._client = boto3.client("bedrock-runtime", region_name=provider.region)

    def generate(self, system_prompt: str, user_prompt: str) -> BedrockResponse:
        """
        Bedrockモデルにプロンプトを送り、テキスト応答を取得する。

        Args:
            system_prompt (str): システムメッセージ。
            user_prompt (str): ユーザーメッセージ。

        Returns:
            BedrockResponse: モデルのテキストと生レスポンス。

        Example:
            >>> resp = llm.generate("system", "user")  # doctest: +SKIP
            >>> resp.text  # doctest: +SKIP
            '...'
        """
        body = self._build_anthropic_body(system_prompt, user_prompt)
        response = self._client.invoke_model(
            **self._build_invoke_kwargs(),
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        payload = json.loads(response["body"].read())
        text = self._extract_text(payload)
        return BedrockResponse(text=text, raw=payload)

    def _build_anthropic_body(self, system_prompt: str, user_prompt: str) -> Dict[str, object]:
        """
        Anthropicメッセージ形式のリクエストボディを作る。

        Args:
            system_prompt (str): システム指示文。
            user_prompt (str): ユーザー質問。

        Returns:
            Dict[str, object]: Bedrock Runtimeへ送るJSON。

        Example:
            >>> body = llm._build_anthropic_body("sys", "usr")  # doctest: +SKIP
            >>> body["system"]  # doctest: +SKIP
            'sys'
        """
        return {
            "anthropic_version": self.ANTHROPIC_VERSION,
            "max_tokens": self._model_cfg.max_tokens,
            "temperature": self._model_cfg.temperature,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_prompt,
                        }
                    ],
                }
            ],
        }

    def _build_invoke_kwargs(self) -> Dict[str, str]:
        """
        invoke_modelに渡す引数を決定する。

        Returns:
            Dict[str, str]: modelId もしくは inferenceProfileArn を含む辞書。

        Raises:
            ValueError: どちらの設定も存在しない場合。

        Example:
            >>> llm._build_invoke_kwargs()  # doctest: +SKIP
            {'modelId': '...'}
        """
        if self._model_cfg.inference_profile_arn:
            return {"inferenceProfileArn": self._model_cfg.inference_profile_arn}
        if self._model_cfg.model_id:
            return {"modelId": self._model_cfg.model_id}
        raise ValueError("Either model_id or inference_profile_arn must be set for the LLM config")

    @staticmethod
    def _extract_text(payload: Dict[str, object]) -> str:
        """
        Bedrockレスポンスからテキスト部分のみを抽出する。

        Args:
            payload (Dict[str, object]): invoke_modelのJSON応答。

        Returns:
            str: 連結済みのテキスト。

        Example:
            >>> BedrockLLM._extract_text({"content": []})
            ''
        """
        contents: List[Dict[str, str]] = payload.get("content", [])  # type: ignore[assignment]
        text_chunks = [chunk.get("text", "") for chunk in contents if chunk.get("type") == "text"]
        return "\n".join([chunk for chunk in text_chunks if chunk])


class LangChainBedrockLLM(LLM):
    """
    LangChain互換のLLM。内部でBedrockLLMを呼び出して結果を保持する。
    """

    latest_response: Optional[BedrockResponse] = None
    _backend: BedrockLLM = PrivateAttr()
    _system_prompt: str = PrivateAttr()

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, backend: BedrockLLM, system_prompt: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._backend = backend
        self._system_prompt = system_prompt

    @property
    def _llm_type(self) -> str:  # pragma: no cover - simple descriptor
        return "bedrock"

    @property
    def _identifying_params(self) -> Dict[str, object]:  # pragma: no cover - simple descriptor
        return {"model_id": self._backend._model_cfg.model_id}

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
    ) -> str:
        """
        LangChainのLLMインターフェース。system_promptは初期化時に固定し、user_promptとして受け取る。
        """
        del stop, run_manager
        response = self._backend.generate(system_prompt=self._system_prompt, user_prompt=prompt)
        self.latest_response = response
        return response.text
