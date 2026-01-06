# rag-research-agent-template 用語メモ

## グラフ構成
- index_graph: ドキュメントを受け取り、インデックスへ登録する処理。
- retrieval_graph: ユーザーの質問を受けて検索し、回答を生成する処理。
- researcher_graph: retrieval_graph の下位グラフ。調査計画→複数クエリで検索→結果統合を担当。

## 基本要素
- graph.py: グラフ（処理の流れ）定義ファイル。
- state.py: グラフ内で受け渡すデータ構造の定義。
- configuration.py: グラフ実行時の設定定義（モデル・検索設定など）。
- prompts.py: LLMに渡すプロンプト定義。

## ディレクトリ
- src/index_graph/: インデックス登録用グラフの実装。
- src/retrieval_graph/: 検索・回答用グラフの実装。
- src/shared/: 共通処理（検索/ユーティリティ/設定）。
- src/sample_docs.json: デモ用のサンプル文書。

## 実行と可視化
- LangGraph Studio: グラフの可視化・デバッグ用UI。

## 検索関連
- retriever: 検索実行の処理（ベクタ検索など）。
- index: 検索対象の保存領域（OpenSearchなど）。
