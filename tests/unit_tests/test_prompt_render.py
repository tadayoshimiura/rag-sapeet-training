import json
from pathlib import Path

from pipelines.question_gen.prompts import build_system_prompt, build_user_prompt
from pipelines.summary_gen.prompts import build_summary_system_prompt

SAMPLE_QUESTION_GEN_INPUTS = {
    "course_id": "course_id=python_beginner",
    "lecture_id": "lecture_python_01",
    "test_genre": "comprehension",
    "requested_count": 1,
    "optional_course_level": "beginner",
}

SAMPLE_AURORA_VARS = {
    "genre_id": "genre_programming",
    "subgenre_id": "subgenre_python_basics",
    "tags": ["topic:python", "skill:syntax"],
    "skills_to_learn": ["skill:variables", "skill:control_flow"],
    "course_name": "Python初級",
    "course_description": "Python初級の基礎講義",
    "course_difficulty": "beginner",
    "lecture_title": "Python基礎",
    "lecture_heading": "変数と制御構文",
    "lecture_description": "変数、型、if/forの基本を学ぶ",
    "lecture_material_type": "pdf",
    "scene_type": "understanding_test",
    "pass_criteria": "80点以上合格",
    "proficiency_rubric": "S/A/B/C/D",
    "scene_target_items": "変数/型/条件分岐/繰り返し",
    "num_candidates": 20,
    "max_adopt": 20,
    "num_questions_in_exam": 10,
}

SAMPLE_SUMMARY_INPUTS = {
    "course_id": "course_id=python_beginner",
    "lecture_id": "lecture_python_01",
}

SAMPLE_INSTRUCTION = "Pythonの初級の問題を作成してください。"


def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start == -1:
        return ""
    end = text.find(end_marker, start)
    if end == -1:
        end = len(text)
    return text[start:end]


def test_question_gen_prompt_uses_db_keys():
    system = build_system_prompt()
    schema = _extract_section(system, "【JSONスキーマ（必須）】", "【TEST_GENRE別")

    # 可視化用のサンプル値（実運用の入力イメージ）
    assert SAMPLE_QUESTION_GEN_INPUTS["course_id"] == "course_id=python_beginner"
    assert SAMPLE_QUESTION_GEN_INPUTS["lecture_id"] == "lecture_python_01"
    assert SAMPLE_QUESTION_GEN_INPUTS["test_genre"] == "comprehension"
    assert SAMPLE_QUESTION_GEN_INPUTS["requested_count"] == 1
    assert SAMPLE_QUESTION_GEN_INPUTS["optional_course_level"] == "beginner"
    print("[question_gen inputs]", SAMPLE_QUESTION_GEN_INPUTS)
    print("[question_gen schema]", schema)
    print("[question_gen system_prompt]", system)

    user_prompt = build_user_prompt(
        contexts=[{"chunk_id": "c1", "text": "ダミーの講義チャンク"}],
        course_id=SAMPLE_QUESTION_GEN_INPUTS["course_id"],
        lecture_id=SAMPLE_QUESTION_GEN_INPUTS["lecture_id"],
        test_genre=SAMPLE_QUESTION_GEN_INPUTS["test_genre"],
        requested_count=SAMPLE_QUESTION_GEN_INPUTS["requested_count"],
        optional_course_level=SAMPLE_QUESTION_GEN_INPUTS["optional_course_level"],
        past_questions_string_data="",
        tbd=SAMPLE_AURORA_VARS,
    )
    user_prompt = user_prompt + "\n追加命令:\n" + SAMPLE_INSTRUCTION + "\n"
    print("[question_gen user_prompt]", user_prompt)

    assert "question_text" in schema
    assert "question_type" in schema
    assert "points" in schema
    assert "options" in schema
    assert "option_text" in schema
    assert "is_correct" in schema

    # 旧スキーマが混ざっていないかを確認
    assert "prompt" not in schema
    assert "answer" not in schema
    assert "difficulty" not in schema


def test_summary_prompt_has_json_output_contract():
    system = build_summary_system_prompt()

    # 可視化用のサンプル値（実運用の入力イメージ）
    assert SAMPLE_SUMMARY_INPUTS["course_id"] == "course_id=python_beginner"
    assert SAMPLE_SUMMARY_INPUTS["lecture_id"] == "lecture_python_01"
    print("[summary inputs]", SAMPLE_SUMMARY_INPUTS)
    print("[summary prompt head]", system.splitlines()[:20])

    assert "出力は JSON 配列のみ" in system
    assert '"summary"' in system
    assert '"skills"' in system
