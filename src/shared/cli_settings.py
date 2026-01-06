"""パイプライン共通の設定読み込み。"""
from __future__ import annotations

import json
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
        base / "configs" / "llm_pipeline_settings.json",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if not path:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
