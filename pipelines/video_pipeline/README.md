# 映像→テキスト→RAG 前処理（独立パイプライン）

`docs/rag_video_pipeline.md` の設計に従い、講座フォルダ（動画・PDFなど）をテキスト化して `course_store/knowledge_md/v1` を生成します。既存RAG資産は汚さない前提で、この配下にパイプライン関連のコード・依存を集約します。

## 重要ポイント
- 講座単位のS3構成（`course_id=test_00` 形式）を前提に `raw/` → `processed/` → `course_store/knowledge_md/v1` の一方向パイプライン。
- 動画は S3 に保管し、処理は「音声抽出→分割→ASR→Markdown整形」で進める。
- PDFは「テキスト層があれば抽出、なければOCR（差し替え可能）」の方針。
- Dify等でフォルダ名が保持されないケースに備え、Markdown先頭にメタ情報（`course_id/lecture_id/category/source_path/source_type`）を付与する。

## 主要コンポーネント
- `config.py`: 設定（ハードコード回避）。
- `layout.py`: S3パス計算。
- `pipeline.py`: オーケストレーション（動画・PDF）。
- `markdown_formatter.py`: LLMでMarkdown整形（長文は自動チャンク分割）。
- `pdf_processor.py`: PDFのテキスト層判定・抽出/OCR分岐。

## 運用メモ
- 同期と差分処理は `./scripts/run_pipeline.sh` で実行（設定は `configs/s3_sync.env`）。
- 既知の未実装:
  - S3のパスをメタDBへ登録する処理（必要なら既存のインデクサ/メタ更新を別途実行）。
  - RAG用インデックス作成（別プロセス前提）。
