# Minimum Ops (Repo Baseline)

This is the minimal operational baseline for this repo.

## Tests (no external API)

```bash
# prompt rendering
<VENV_PYTHON> -m pytest -s tests/unit_tests/test_prompt_render.py

# mocked integration (question_gen + summary)
<VENV_PYTHON> -m pytest -s tests/integration_tests/test_llm_pipelines.py
```

## Question generation (Bedrock)

```bash
AWS_PROFILE=ReadWrite12-480160868418 \
<VENV_PYTHON> scripts/entry/run_question_gen.py \
  --kb-dir /Users/tadayoshi_miura/workspace/prepare/s3/course_store/course_id=test_00/knowledge_md \
  --course-id course_id=test_00 \
  --lecture-id lecture_a \
  --test-genre comprehension \
  --requested-count 1 \
  --optional-course-level beginner \
  --out <REPO_ROOT>/outputs/question_gen.json
```

Notes:
- `<VENV_PYTHON>` is the full path to your virtualenv python.
- `<REPO_ROOT>` is the path to this repository.

## Batch run (manual)

Run multiple jobs by looping the command above with different
`--lecture-id`, `--test-genre`, and `--requested-count`.
