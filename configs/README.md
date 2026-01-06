# configs について

このフォルダは、パイプライン共通の設定ファイルを集約します。運用で迷わないように、用途ごとに分離しています。

## ファイル一覧

- `bedrock_kb_config.env`
  - Bedrock Knowledge Bases のID設定（KB ID / Data Source ID）。
- `csv_settings.yml`
  - CSV列マッピングとCSVジャンル推定ルールをまとめた設定。
- `rag_runtime_dev.json`
  - 開発用のRAG設定。
  - LLM設定（`llm_models`）、`summary_settings`、vector_store設定を含む。
- `s3_sync.env`
  - S3同期・バックアップ・タイムアウトなどの共通環境変数。
- `system_prompts.json`
  - System Prompt の管理（問題生成/要約/ルーターなど）。

## 運用メモ

- 設定は **原則このフォルダに集約** し、スクリプトやコードへのハードコードは避けます。
- 追加する場合は、用途が分かる名前にし、ここへ説明を追記してください。

## System Prompt 運用

- System Prompt は `configs/system_prompts.json` に集約する。
- question/summary/router/retrieval などのキー名は **固定** とし、コード側もこのキーを参照する。
- 追加・変更した場合は、同ファイル内のキー一覧を更新する。

## system_prompts.json のキー一覧

- `router_prompt`
- `question_gen_prompt`
- `retrieval_general_prompt`
- `retrieval_generate_queries_prompt`
- `retrieval_more_info_prompt`
- `retrieval_research_plan_prompt`
- `retrieval_response_prompt`
- `retrieval_router_prompt`
- `summary_gen_prompt`
- `summary_rewrite_prompt`
