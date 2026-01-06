# 移植計画（現時点版）

## 目的
- 自作RAGシステムを `rag-research-agent-template` に移植し、テンプレの index_graph / retrieval_graph を活用する。
- 動画→文字起こし/要約/問題生成のパイプラインは維持し、将来テンプレの共通部品へ統合できる余地を残す。
- 評価系（eval_system）は分離を維持し、移植対象外とする。

## 方針
- `src/` はテンプレ既存のまま活用し、**新規コードは `pipelines/` 配下に置く**。
- index_graph / retrieval_graph を使う。
- Embeddings は Bedrock の Cohere 系（モデルIDは未定）。
- LLM は Bedrock Claude（既存自作システムのモデルIDを使用）。
- 設定は `configs/` に集約し、ハードコードは避ける。
- 検索基盤は OpenSearch を想定（サーバレス前提、PoCではローカルでも可）。

## 実装済み
- Bedrock対応の追加
  - `src/shared/retrieval.py`: `bedrock` プロバイダ追加（BedrockEmbeddings）
  - `src/shared/utils.py`: `bedrock` プロバイダ追加（ChatBedrock）
  - `pyproject.toml`: `langchain-aws` 追加

## 未実施（次の作業）
- 既存コードの配置
  - `question_gen/`, `summary_gen/`, `video_pipeline/`, `rag_core/` を `pipelines/` 配下へ移植
  - `scripts/*` を `scripts/` 配下へ移植
  - `configs/*` を `configs/` に移植
  - `docs/*` を `docs/` に移植（評価系は除外）
- BedrockモデルIDの設定値を `configs/` に追加（モデルIDは未確定のため空欄/仮）
- index_graph による knowledge_md の索引化（md単位）
- OpenSearch へ接続する retriever_provider の拡張（設定/実装の追加）

## 後回しにする項目（先にしない）
- Bedrock のモデルID確定（Claude / Cohere は動作テスト直前に決定）
- OpenSearch の本番パラメータ確定（URL / 認証 / Index 命名）
- index_graph を使った本番索引化の運用設計（PoC後に決定）
- パイプラインの本実行（差分処理の実データ処理は後で実施）
（移動済み）

## 実施済み
- Bedrock Knowledge Bases の取り込み実行（job_id を記録して完了確認）

## 移植対象外
- `eval_system/`（評価システムは完全分離）
- `s3/`（データは移植対象外）

## 依存
- `langchain-aws` が必須（Bedrock利用のため）
- AWS_REGION / AWS_DEFAULT_REGION の指定が必須
