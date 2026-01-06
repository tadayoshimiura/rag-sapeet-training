import json
from typing import Any

from pipelines.question_gen.llm_pipeline import generate_json_array
from pipelines.question_gen.prompts import build_system_prompt, build_user_prompt
from pipelines.summary_gen.prompts import build_summary_system_prompt
from scripts.entry.run_summary_gen import _build_user_prompt as build_summary_user_prompt


class _DummyLLM:
    def generate(self, system: str, user: str, max_tokens: int, temperature: float) -> str:  # noqa: D401
        raise RuntimeError("Dummy LLM should not be called directly")


def _validate_question_schema(item: dict[str, Any]) -> None:
    base_keys = {
        "question_text",
        "question_type",
        "weight_flag",
        "points",
        "explanation",
        "evidence",
        "is_canonical",
        "course_id",
        "lecture_id",
        "tags",
    }
    assert isinstance(item.get("evidence"), dict)
    assert "chunk_id" in item["evidence"]
    assert "quote" in item["evidence"]

    qtype = item.get("question_type")
    assert qtype in {"single_choice", "multiple_choice", "text"}

    if qtype in {"single_choice", "multiple_choice"}:
        base_keys = base_keys | {"options"}
        assert isinstance(item.get("options"), list)
        for opt in item["options"]:
            assert set(opt.keys()) == {"option_text", "is_correct"}
    else:
        assert "options" not in item

    assert set(item.keys()) == base_keys


def _validate_summary_schema(item: dict[str, Any]) -> None:
    assert set(item.keys()) == {"course_id", "lecture_id", "summary", "skills"}
    assert isinstance(item["skills"], list)


def test_question_gen_pipeline_mocked(tmp_path):
    system = build_system_prompt()
    user = build_user_prompt(
        contexts=[{"chunk_id": "c1", "text": "Sample"}],
        course_id="course_id=test_00",
        lecture_id="lecture_a",
        test_genre="comprehension",
        requested_count=1,
        optional_course_level="beginner",
        past_questions_string_data="",
        tbd={},
    )

    output = [
        {
            "question_text": "テスト質問",
            "question_type": "single_choice",
            "weight_flag": 2,
            "points": 20,
            "explanation": "解説",
            "evidence": {"chunk_id": "c1", "quote": "Sample"},
            "is_canonical": True,
            "course_id": "course_id=test_00",
            "lecture_id": "lecture_a",
            "tags": ["topic:test"],
            "options": [
                {"option_text": "A", "is_correct": True},
                {"option_text": "B", "is_correct": False},
            ],
        }
    ]

    def fake_generate(system_text: str, user_text: str, max_tokens: int, temperature: float) -> str:
        assert "question_text" in system_text
        assert "contexts" in user_text
        return json.dumps(output, ensure_ascii=False)

    payload = generate_json_array(
        _DummyLLM(),
        system,
        user,
        raw_base=str(tmp_path / "question_gen"),
        raw_suffix="raw",
        max_tokens=500,
        temperature=0.0,
        generate_fn=fake_generate,
    )

    print("[question_gen payload]", json.dumps(payload, ensure_ascii=False))

    assert isinstance(payload, list)
    assert len(payload) == 1
    _validate_question_schema(payload[0])


def test_summary_gen_pipeline_mocked():
    system = build_summary_system_prompt()
    user = build_summary_user_prompt(
        contexts=[{"chunk_id": "c1", "text": "Sample"}],
        variables={"course_id": "course_id=test_00", "lecture_id": "lecture_a"},
    )

    output = [
        {
            "course_id": "course_id=test_00",
            "lecture_id": "lecture_a",
            "summary": "これは要約です。",
            "skills": ["skill:a"],
        }
    ]

    def fake_generate(system_text: str, user_text: str, max_tokens: int, temperature: float) -> str:
        assert "JSON 配列" in system_text
        assert "contexts" in user_text
        return json.dumps(output, ensure_ascii=False)

    raw = fake_generate(system, user, 500, 0.0)
    payload = json.loads(raw)
    print("[summary payload]", json.dumps(payload, ensure_ascii=False))
    assert isinstance(payload, list)
    assert len(payload) == 1
    _validate_summary_schema(payload[0])
