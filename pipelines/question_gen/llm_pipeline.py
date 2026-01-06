"""問題生成のLLM実行ロジック。"""
from __future__ import annotations

import json
from typing import Callable

from shared.bedrock_llm import BedrockLLM
from shared.output_utils import append_suffix, write_text


def extract_json_array_text(text: str) -> str:
    """出力からJSON配列部分だけを切り出す（失敗時は元文字列を返す）。

    引数:
        text: LLM出力の生文字列。

    戻り値:
        JSON配列に見える部分、または元の文字列。

    例:
        >>> extract_json_array_text('xx[{"a":1}]yy')
        '[{"a":1}]'
    """
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]


def strict_json_hint() -> str:
    """JSON崩れを減らすための追加指示（日本語）。"""
    return (
        "\n\n【出力フォーマットの追加制約】\n"
        "- 出力はJSON配列（[...]）のみ。\n"
        "- ダブルクォート(\")のみを使用（シングルクォート禁止）。\n"
        "- 末尾カンマ禁止。\n"
        "- JSON以外の文字（説明、コードブロック、前置き、後置き）は一切出力しない。\n"
    )


def parse_json_array_with_repair(
    llm: BedrockLLM,
    system: str,
    raw_text: str,
    *,
    max_tokens: int = 2000,
    generate_fn: Callable[[str, str, int, float], str] | None = None,
) -> list:
    """JSON配列として読めるまで最小限の修復を行う。

    引数:
        llm: LLMクライアント。
        system: System Prompt本文。
        raw_text: LLMの生出力。
        max_tokens: 修復時の最大トークン。
        generate_fn: LLM呼び出し関数（省略時は llm.generate）。

    戻り値:
        JSON配列として読み込んだPythonリスト。

    例:
        >>> parse_json_array_with_repair(llm, "役割:", '[{"summary":"x"}]')[0]["summary"]
        'x'
    """
    candidates = [raw_text, extract_json_array_text(raw_text)]
    last_err: Exception | None = None
    for c in candidates:
        try:
            return json.loads(c)
        except Exception as e:  # noqa: BLE001
            last_err = e

    repair_user = (
        "次のテキストは、本来 JSON配列（[]）のみを出力すべきところ、JSONとして壊れています。\n"
        "仕様どおりの JSON配列だけに修正して出力してください（JSON以外の文章は禁止）。\n\n"
        "---- 入力 ----\n"
        f"{extract_json_array_text(raw_text)}\n"
        "---- 入力ここまで ----\n"
    )
    generate = generate_fn or (lambda s, u, m, t: llm.generate(system=s, user=u, max_tokens=m, temperature=t))
    repaired = generate(system, repair_user, max_tokens, 0.0)
    try:
        return json.loads(extract_json_array_text(repaired))
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"JSONの解析に失敗しました: {last_err} / 修復後: {e}") from e


def generate_json_array(
    llm: BedrockLLM,
    system: str,
    user: str,
    *,
    raw_base: str,
    raw_suffix: str,
    max_tokens: int,
    temperature: float,
    attempts: int = 3,
    generate_fn: Callable[[str, str, int, float], str] | None = None,
) -> list:
    """LLM出力をJSON配列として取得する（rawログ保存と再試行付き）。

    引数:
        llm: LLMクライアント。
        system: System Prompt本文。
        user: User Prompt本文。
        raw_base: rawログの基準パス。
        raw_suffix: rawログの種別サフィックス。
        max_tokens: 生成上限トークン。
        temperature: 生成温度。
        attempts: 試行回数。
        generate_fn: LLM呼び出し関数（省略時は llm.generate）。

    戻り値:
        JSON配列として読み込んだPythonリスト。

    例:
        >>> isinstance(generate_json_array(llm, "役割:", "入力", raw_base="out", raw_suffix="raw", max_tokens=10, temperature=0.0), list)  # doctest: +SKIP
        True
    """
    last_error: Exception | None = None
    generate = generate_fn or (lambda s, u, m, t: llm.generate(system=s, user=u, max_tokens=m, temperature=t))
    for attempt in range(1, attempts + 1):
        text = generate(system, user, max_tokens, temperature)
        write_text(append_suffix(raw_base, f".{raw_suffix}{attempt}.txt"), text)
        try:
            return parse_json_array_with_repair(
                llm,
                system,
                text,
                max_tokens=max_tokens,
                generate_fn=generate,
            )
        except Exception as e:  # noqa: BLE001
            last_error = e
            user = user + strict_json_hint()
    raise RuntimeError(f"JSON生成に失敗しました: {last_error}")
