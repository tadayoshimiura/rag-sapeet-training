"""要約生成プロンプトの組み立て。"""
from __future__ import annotations

from shared.prompt_store import load_system_prompt


def build_summary_system_prompt() -> str:
    """要約生成のSystem Promptを返す。

    引数:
        なし。

    戻り値:
        System Prompt本文。

    例:
        >>> build_summary_system_prompt()[:5]
        '役割:'
    """
    return load_system_prompt("summary_gen_prompt")


def build_summary_rewrite_system_prompt() -> str:
    """要約の文字数調整用System Promptを返す。

    引数:
        なし。

    戻り値:
        System Prompt本文。

    例:
        >>> build_summary_rewrite_system_prompt()[:5]
        '役割:'
    """
    return load_system_prompt("summary_rewrite_prompt")
