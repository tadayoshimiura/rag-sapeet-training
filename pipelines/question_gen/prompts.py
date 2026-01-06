"""問題生成プロンプトの組み立て。"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from shared.prompt_store import load_system_prompt

def build_system_prompt() -> str:
    """問題生成のSystem Promptを返す。

    Returns:
        System Prompt本文。

    Examples:
        >>> build_system_prompt()[:5]
        '役割:'
    """
    return load_system_prompt("question_gen_prompt")


def build_user_prompt(
    contexts: List[dict],
    course_id: str,
    lecture_id: str,
    test_genre: str,
    requested_count: int,
    optional_course_level: str,
    past_questions_string_data: str,
    tbd: Dict[str, Any],
) -> str:
    """User Prompt（入力変数を具体値で埋める）。

    Args:
        contexts: {contexts} の配列。
        course_id: course_id の値。
        lecture_id: lecture_id の値。
        test_genre: comprehension/skill/followup のいずれか。
        requested_count: 生成件数。
        optional_course_level: beginner/intermediate/advanced のいずれか。
        past_questions_string_data: 既出問題の文字列。
        tbd: TBD変数の辞書。

    Returns:
        User Prompt本文。

    Examples:
        >>> build_user_prompt([], "course_id=test_00", "lecture_a", "comprehension", 10, "beginner", "", {})
        '以下の入力変数をセットします。これらに基づき、JSON配列のみを出力してください。\\n\\ncourse_id=course_id=test_00\\n'
    """
    # contexts はJSON配列として渡す（監査/デバッグ用途）
    tbd_lines = []
    for k, v in (tbd or {}).items():
        tbd_lines.append(f"{k}={v}")
    tbd_block = "\n".join(tbd_lines)

    return (
        "ユーザー指示に従い、以下の条件で問題を生成してください。出力はJSON配列のみ。\n\n"
        f"course_id={course_id}\n"
        f"lecture_id={lecture_id}\n"
        f"test_genre={test_genre}\n"
        f"requested_count={requested_count}\n"
        f"optional_course_level={optional_course_level}\n\n"
        "past_questions_string_data:\n"
        f"{past_questions_string_data}\n\n"
        + (f"{tbd_block}\n\n" if tbd_block else "")
        + "contexts:\n"
        f"{json.dumps(contexts, ensure_ascii=False)}\n"
    )
