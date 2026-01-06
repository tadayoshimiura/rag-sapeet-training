"""BedrockのLLM呼び出しを共通化する。"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import (
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)


@dataclass
class BedrockLLM:
    """Bedrockを使ってテキスト生成する共通クラス。"""

    model_id: str
    region: Optional[str] = None
    read_timeout_s: int = 300
    connect_timeout_s: int = 10
    max_attempts: int = 5
    retry_sleep_s: int = 3

    def __post_init__(self) -> None:
        region = self.region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
        if not region:
            raise ValueError("AWS_REGION が未設定です")
        read_timeout = int(os.getenv("BEDROCK_READ_TIMEOUT", self.read_timeout_s))
        connect_timeout = int(os.getenv("BEDROCK_CONNECT_TIMEOUT", self.connect_timeout_s))
        max_attempts = int(os.getenv("BEDROCK_MAX_ATTEMPTS", self.max_attempts))
        retry_sleep_s = int(os.getenv("BEDROCK_RETRY_SLEEP", self.retry_sleep_s))
        cfg = Config(
            read_timeout=read_timeout,
            connect_timeout=connect_timeout,
            retries={"max_attempts": max_attempts, "mode": "standard"},
        )
        self.client = boto3.client("bedrock-runtime", region_name=region, config=cfg)
        self.read_timeout_s = read_timeout
        self.connect_timeout_s = connect_timeout
        self.max_attempts = max_attempts
        self.retry_sleep_s = retry_sleep_s

    def generate(self, system: str, user: str, max_tokens: int = 4000, temperature: float = 0.0) -> str:
        """Bedrockに問い合わせてテキストを生成する（タイムアウト時は再試行）。"""
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [{"role": "user", "content": [{"type": "text", "text": user}]}],
            "system": [{"type": "text", "text": system}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        body = json.dumps(payload).encode("utf-8")

        last_err: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                resp = self.client.invoke_model(
                    modelId=self.model_id,
                    body=body,
                    contentType="application/json",
                    accept="application/json",
                )
                result = resp.get("body")
                if hasattr(result, "read"):
                    result = result.read()
                data = json.loads(result)
                return data["content"][0]["text"]
            except (ReadTimeoutError, EndpointConnectionError, ConnectionClosedError, ConnectTimeoutError) as e:
                last_err = e
                if attempt >= self.max_attempts:
                    break
                time.sleep(self.retry_sleep_s * attempt)

        raise RuntimeError(f"Bedrock呼び出しがタイムアウトしました: {last_err}")
