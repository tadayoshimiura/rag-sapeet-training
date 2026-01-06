# RAGシステム（Sapeet Training）

このリポジトリは、Sapeetの教材向けRAGシステムの実装をまとめたものです。  
デフォルト運用は **Amazon Bedrock Knowledge Base** を前提とします。

## クイックスタート

1. `.env` を作成します。

```bash
cp .env.example .env
```

2. 最小の問題生成（Bedrock）を実行します。

```bash
AWS_PROFILE=ReadWrite12-480160868418 \
/Users/tadayoshi_miura/workspace/prepare/.venv_py313/bin/python scripts/entry/run_question_gen.py \
  --kb-dir /Users/tadayoshi_miura/workspace/prepare/s3/course_store/course_id=test_00/knowledge_md \
  --course-id course_id=test_00 \
  --lecture-id lecture_a \
  --test-genre comprehension \
  --requested-count 1 \
  --optional-course-level beginner \
  --out /Users/tadayoshi_miura/workspace/outputs/question_gen.json
```

## 最小運用（RAGシステム）

`docs/minimum_ops.md` に以下をまとめています。
- プロンプトのレンダリングテスト
- モック統合テスト
- Bedrockでの問題生成コマンド

Auroraマッピングの確認は `docs/aurora_mapping.md` を参照してください。  
フォーク／リネーム／シークレット運用は `docs/repo_setup.md` を参照してください。

## 仕組み（平易な説明）

- **System Prompt**: モデル全体のルール
  - `configs/system_prompts.json`（`question_gen_prompt`, `summary_gen_prompt`, `router_prompt`）
- **User Prompt**: 実際に与える入力変数
  - 問題生成: `pipelines/question_gen/prompts.py`
  - 要約: `scripts/entry/run_summary_gen.py`
- **Router**: ユーザーの指示から使うプロンプトを判定
  - `scripts/entry/run_llm_pipeline.py` が `router_prompt` とキーワード判定を使用

## モデルのデフォルト設定

`configs/rag_runtime_dev.json` に定義しています。
- モデル設定は `.env` に集約（`RAG_LLM_MODEL_ID` / `RAG_LLM_REGION`）
- デフォルトは Bedrock（`.env.example` を参照）

## 環境情報の安全運用

- 秘密情報は `.env` に置きます（コミット禁止）。
- `.env` / `outputs/` / `logs/` / `reports/` は `.gitignore` 済みです。
- `.env.example` が公開用テンプレです。

## バッチ運用（任意）

手動バッチは `docs/minimum_ops.md` のコマンドをループ実行してください。  
SQSを導入する場合、キューのペイロードは以下を想定しています。
- `lecture_id`
- `test_genre`
- `question_count`

ワーカー側は `scripts/entry/run_question_gen.py` をジョブ単位で呼び出します。
