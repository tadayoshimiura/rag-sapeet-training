# 問題生成（独立）

このディレクトリは、講座Markdown（`course_store/.../knowledge_md/v1`）から `{contexts}` を構築し、
問題生成（JSON出力）までをローカルで実行するためのコードを置きます。

方針:
- 根拠は `{contexts}` のみ。
- `test_genre` / `optional_course_level` は出力JSONに必須。
- `lecture_id` は Markdownヘッダ（またはフォルダ構成）から自動推定する。
- 既存の `video_pipeline/` とは独立（別システム）。
