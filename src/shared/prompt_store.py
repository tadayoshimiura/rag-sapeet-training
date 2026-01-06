"""System Promptの読み込み。"""
from __future__ import annotations

import json
from pathlib import Path


def load_system_prompt(prompt_id: str) -> str:
    """System PromptをJSONから取得する。"""
    base = Path(__file__).resolve().parents[2]
    store_path = base / "configs" / "system_prompts.json"
    if not store_path.exists():
        raise FileNotFoundError("system_prompts.json が見つかりません")
    data = json.loads(store_path.read_text(encoding="utf-8"))
    if prompt_id not in data:
        raise KeyError(f"System Promptが見つかりません: {prompt_id}")
    return data[prompt_id]
