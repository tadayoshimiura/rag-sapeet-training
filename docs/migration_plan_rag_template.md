# rag-research-agent-template 移植計画（決定事項）

## 基本方針
- rag-research-agent-template の index_graph / retrieval_graph を最大限活用する。
- 既存の動画→テキスト化パイプラインは外部パイプラインとして維持し、knowledge_md を取り込む。
- 評価システムは移植対象外。

## 取り込み単位
- md 単位で index_graph に投入する（`knowledge_md/v1/<lecture_id>/*.md`）。

## 検索基盤
- OpenSearch Serverless を採用する。
- インデックスはコース別で分割する（検索対象をコース単位で分離）。
- 命名規則（PoC）: `course_{course_id}`（例: `course_test_00`）。

## メタデータ（PoCは多め）
PoCでは以下を全て付与し、本番で不要なものを削る方針。
- course_id
- lecture_id
- source_path
- source_type
- title
- chunk_id
- category
- genre_id
- subgenre_id
- tags
- skills_to_learn
- course_name
- course_description
- course_difficulty
- lecture_title
- lecture_heading
- lecture_description
- lecture_material_type
- test_genre
- optional_course_level

## LangGraphの利用範囲
- index_graph も利用する（knowledge_md の取り込み入口にする）。

## データ流し込み
- PoC: ローカル同期 → index_graph 取り込み。
- 本番: S3直読み → index_graph 取り込み。

## LLM/Embedding
- LLMは Bedrock の Claude 系を継続利用。
- Embeddingは BedrockのCohere系を検討（暫定）。

## ECS実行単位
- index用タスクと retrieval用タスクを分離して運用する。
- 理由: スケール特性が異なるため、コスト/安定性を分離する。
