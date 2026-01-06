# 最小運用（レポジトリ基準）

このリポジトリの最低限の運用手順です。

## テスト（外部APIなし）

```bash
# プロンプトのレンダリング
<VENV_PYTHON> -m pytest -s tests/unit_tests/test_prompt_render.py

# モック統合（question_gen + summary）
<VENV_PYTHON> -m pytest -s tests/integration_tests/test_llm_pipelines.py
```

## 問題生成（Bedrock）

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

メモ:
- `<VENV_PYTHON>` は仮想環境の python のフルパス。
- `<REPO_ROOT>` はこのリポジトリのルートパス。

## バッチ実行（手動）

上記コマンドをループし、
`--lecture-id` / `--test-genre` / `--requested-count` を変えて実行します。
