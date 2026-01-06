# テンプレ差分の分類

このドキュメントは、現行リポジトリと元テンプレの差分を
「準拠」「拡張」「逸脱」の3分類で整理したものです。

## 準拠（テンプレ保持）
- 主要構造は維持: `src/index_graph/`, `src/retrieval_graph/`, `langgraph.json`
- 主要入口は維持（graphモジュールと基本設定）
- トップレベルの基本構成を保持（README/Makefile/tests）

## 拡張（追加）
- `configs/` 追加（Bedrock/OpenSearch/KB設定・プロンプト）
- `pipelines/` 追加（question_gen/summary_gen/video_pipeline/rag_core）
- `scripts/` 追加（ローカル実行・バッチの入口）
- `docs/` 拡充（運用/runbook/評価メモ）
- `src/shared/` 拡張（Bedrock・prompt関連）
- `tests/` 拡張（サンプルケース・追加テスト）

## 逸脱（挙動変更）
- `src/retrieval_graph/*` と `src/shared/*` に挙動変更あり
- ルーティング/回答プロンプトが元テンプレと異なる
- 検索系の動作が Bedrock/KB/VectorDB 前提へ拡張
- `.env.example` / `pyproject.toml` を追加スタックに合わせて変更

## 変更理由（詳細）
- `template_diff_reasons.md`
