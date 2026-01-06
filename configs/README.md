# configs について

このフォルダは、パイプライン共通の設定ファイルを集約します。運用で迷わないように、用途ごとに分離しています。

## ファイル一覧

- `bedrock_defaults.json`
  - Bedrock Embeddings のデフォルト設定。
- `bedrock_kb.env`
  - Bedrock Knowledge Bases のID設定（KB ID / Data Source ID）。
- `csv_genre_rules.yml`
  - CSV由来のジャンル推定ルール。
- `csv_mapping.yml`
  - CSVの列マッピング定義。
- `dev.json`
  - 開発用のRAG設定。
- `genre_rules.yml`
  - フォルダ/ファイル名からジャンル推定するルール。
- `llm_pipeline_settings.json`
  - 問題生成・要約生成・contexts などの共通パイプライン設定。
- `opensearch_defaults.json`
  - OpenSearch利用時のデフォルト設定。
- `prod.json`
  - 本番用のRAG設定。
- `requirements-pipeline.txt`
  - パイプライン用の依存関係（必要に応じて使用）。
- `s3_sync.env`
  - S3同期・バックアップ・タイムアウトなどの共通環境変数。
- `summary_settings.json`
  - 要約生成のパラメータ設定。
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
