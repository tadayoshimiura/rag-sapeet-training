"""パイプライン共通の設定読み込み。"""
from __future__ import annotations

import json
import os
from pathlib import Path


def load_llm_pipeline_settings() -> dict:
    """LLMパイプライン設定をJSONから読み込む。

    引数:
        なし。

    戻り値:
        設定辞書（存在しない場合は空）。

    例:
        >>> isinstance(load_llm_pipeline_settings(), dict)
        True
    """
    base = Path(__file__).resolve().parents[2]
    candidates = [
        base / "configs" / "rag_runtime_dev.json",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if not path:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    settings = payload.get("llm_models", {})
    common = settings.setdefault("common", {})
    # .env override for model/region
    env_model = os.getenv("RAG_LLM_MODEL_ID")
    env_region = os.getenv("RAG_LLM_REGION")
    env_embed = os.getenv("RAG_EMBEDDING_MODEL_ID")
    if not env_model or not env_region:
        raise ValueError("RAG_LLM_MODEL_ID と RAG_LLM_REGION を .env に設定してください")
    common["model_id"] = env_model
    common["region"] = env_region
    if env_embed:
        settings["embedding"] = {"model_id": env_embed}
    return settings
