# 運用メモ（手順書として利用）

## 最優先ルール（厳守）
- 既存のパイプライン/ファイル/モジュールを可能な限り再利用する。
- 新規コードの追加は最小限にする（同じものが使えるなら使う）。
- 共通モジュール/共通クラスを必須とし、コンポーネント化を推進する。
- 開発前に必ず本ドキュメントを読む。
- 仕様の質問は文面の意図を先読みし、運用上の最適形も提案する（今回のような二層要約は先に提示する）。

## 今後の計画メモ（要点だけ）
- System Prompt は現在4つだが、将来的には **9つ** に拡張予定。
- 会社のGitHub組織に fork して運用する予定（未実施）。
  - 元リポジトリURL / 組織名 / フォーク先名を確定してから実施する。
- AWS運用の想定:
  - ECS/ECRを前提に、必要なAWSサービスを調査し、必要なら実装する。
  - 監視/ログ/ジョブ制御の構成もあわせて検討する。
- ASR方針:
  - 可能なら Bedrock で完結したモデル構成に寄せたい。
  - ローカルWhisper依存は将来は避ける方向（現状はWhisper/faster-whisperが既定）。
- 評価システム:
  - 早期実装し、評価軸を定義したらすぐ回せる状態にする。
- OCR:
  - テキスト層判定〜OCR呼び出しの仕組みは実装済み。
  - OCRバックエンドは未確定（差し替え前提）。

## AWS 認証・同期
```bash
# （推奨）同期→差分処理（動画+PDF+CSV）を 1コマンドで実行
./scripts/entry/run_pipeline.sh
```

メモ:
- 実行時は `PYTHONPATH=$PWD:$PWD/src` を前提とする（共通モジュールを参照するため）。
- 実体の設定は `configs/s3_sync.env` に集約（プロファイル/バケット/講座ID/同期元/同期先/Python実行パス）。
- LangGraph 側の既定設定は `configs/bedrock_defaults.json` / `configs/opensearch_defaults.json` に置く（modelId は `configs/` に設定済み）。
- 問題生成/要約の model_id は `configs/llm_pipeline_settings.json` に必ず設定する（未設定なら実行時に停止）。
- `run_pipeline.sh` の中で `aws sso login` を実行するため、基本的に手動ログインは不要。

## 日常運用（最小手順）
1. ローカルの `s3/raw/course_packages/<course_id>/upload/` に動画/PDF/CSVを配置（Iconや`.DS_Store`は置かない）。
2. `./scripts/entry/run_pipeline.sh` を実行（同期→差分処理が自動で走る）。
3. 出力先（S3）:
   - `s3://<bucket>/course_store/<course_id>/knowledge_md/v1/<lecture_id>/*.md`
4. 現在の対応ファイル種別: 動画 / PDF / CSV（この3種のみ）
5. PoC はローカルで停止して良い。本番は下記でローカル→S3を同期する。
   - `./scripts/sync/sync_course_store_to_s3.sh`
4. Dify等でフォルダ名が保持されない場合に備え、Markdown先頭にメタ情報を自動付与:
   - `course_id`, `lecture_id`, `category`, `source_path`, `source_type`
   - `lecture_id` は講義単位の識別子（フォルダ名と同一）。
   - `category` は論理カテゴリ（必要なら別途運用で付与）。

## 差分チェックだけしたい場合
```bash
./scripts/sync/sync_upload.sh --check
```
差分がない場合も `差分なし` を表示します。

## 出力をローカルに揃える（S3→ローカル）
```bash
./scripts/sync/sync_outputs.sh
```
`course_store/.../knowledge_md/v1` と `processed/.../_status.json` をローカルの `s3/` に同期します。
※ `summary.json` と `summary.json.raw*` はローカル正本のため同期で削除されません。

## 出力をS3へ反映する（ローカル→S3）
```bash
./scripts/sync/sync_course_store_to_s3.sh
```
`knowledge_md` と `question_bank` をS3に同期します（同期前にローカルをバックアップ）。

## 失敗時の確認ポイント
- `processed/<course_id>/_status.json` にファイル単位の `errors` が残る（次回は自動で再実行対象になる）。
- SSOログインが必要な場合は `aws sso login --profile ...` がブラウザを開く。

## 設定を変える場合
- 固定値は `configs/s3_sync.env` を編集（バケット名、講座ID、同期元/先、Pythonパスなど）。
- LLM入力が長すぎる場合は `video_pipeline/config.py` の `bedrock_chunk_chars` を調整。
- CSV列の意味が変わる場合は `configs/csv_mapping.yml` を編集（列名→意味の対応）。
- CSVのジャンル自動判定は `configs/csv_genre_rules.yml` でキーワードを設定する。

## 既存出力の移動（1回だけ）
以前の出力が `knowledge_md/v1/from_*` に残っている場合、以下で `knowledge_md/v1/<lecture_id>` に移動できます。
```bash
PYTHONPATH=$PWD AWS_PROFILE=ReadWrite12-480160868418 AWS_REGION=ap-northeast-1 AWS_DEFAULT_REGION=ap-northeast-1 \
./scripts/migrate/migrate_knowledge_md_lectures.py --course-id course_id=test_00 --root s3/course_store/course_id=test_00/knowledge_md/v1
```

question_bank 側で `from_*` が残っている場合は、以下で lecture_id 配下に移動できます。
```bash
/Users/tadayoshi_miura/workspace/prepare/.venv_py313/bin/python \
  scripts/migrate/migrate_question_bank_lectures.py --root s3/course_store/course_id=test_00/question_bank
```

## RAGプロンプト設計メモ（反映事項）
- 根拠は常に `{contexts}` のみ（`rag_chunks` は廃止して `{contexts}` に統一）。
- `course_id` やジャンル/タグ等は「制約・追跡」のための情報であり、講義内容の根拠として使わない。
- `evidence` は必須（`chunk_id` と `quote`）。`quote` は 25語以内。
- 画面設計に存在する要素は入力変数として含めるが、DB/APIのキー名が未確定なものは `{TBD_xxx}` として隔離する（推測で仕様を破綻させない）。

## ジャンル制約（暫定）
- ジャンルID等が未確定でも、運用で「制約（焦点・配分）」を管理できるよう `configs/genre_rules.yml` を用意。
- ここで定義するルールは根拠ではなく制約。根拠は常に `{contexts}` のみ。

## 評価（独立）
- 評価はMT-Bench準拠（LLMジャッジ）を前提に別システムとして実装する（既存のパイプラインやRAG資産とは独立）。
  - 実装: `eval_system/`
  - 実行: `./eval_system/run_eval.py --target question --input-json <path>`
  - 評価結果: `eval_system/eval_results/` に保存（デフォルト）

## Bedrock Knowledge Base 経由の検索（テンプレ疎通）
- ルーターを「KB前提」の判定に寄せる案は**検討中**。
- 現行の設定は `configs/bedrock_kb_defaults.json` を使用。
- 他モデルの候補は以下（コメントアウト扱いの参考）:
  - `# bedrock/anthropic.claude-3-haiku-20240307-v1:0`
  - `# bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0`
- ルーター `more-info` は最小限に抑え、一般質問でも検索に流す設定に調整済み。
- 疎通テスト（一般質問）: 「今日の東京の天気は？」→ 根拠がない旨の回答を確認。
- Bedrock KB 利用時は `index_graph` を使用しない（KB への取り込みは ingestion job のみ）。

## DeepEval（隔離実行）
1. `python3 -m venv eval_system/.venv`
2. `eval_system/.venv/bin/pip install -r eval_system/requirements.txt`
   - Bedrock利用時は `AWS_BEDROCK_MODEL_NAME` / `AWS_BEDROCK_REGION` を設定
3. 入力JSONを用意（配列）
   - 必須: `input`, `actual_output`
   - 任意: `expected_output`, `context`（配列）
4. 実行: `eval_system/.venv/bin/python eval_system/run_deepeval.py --input-json path/to/cases.json`

## 評価用の質問テンプレ（固定セット）
評価をブレさせないため、以下の質問文は「固定のテストケース入力」として維持する。
（値はDify側の変数で注入し、質問文は極力固定）

### TC-01: スキーマ検証（最小）
- 「教材から `{requested_count}` 問の問題を作って。出力は仕様どおりのJSON配列のみ。」

### TC-02: test_genre 分布検証（3Run）
- understanding: 「概念理解と手順再構成を測る問題を `{requested_count}` 問作って。」
- retention: 「取り違えやすい点を狙い、既出と同構造を避けて問題を `{requested_count}` 問作って。」

### TC-03: course_level 比較（2Run）
- beginner: 「初級向けに、基礎確認中心で `{requested_count}` 問作って。」
- advanced: 「上級向けに、条件追加・理由説明・誤り指摘を増やして `{requested_count}` 問作って。」

### TC-04: 既出抑制（1Run）
- 「過去問題（past_questions_string_data）と同じ構造にならないように `{requested_count}` 問作って。」

### ジャンル（暫定）拡張テスト
- programming_like: 「コードレビュー/バグ指摘を含む問題を `{requested_count}` 問作って。」
- business_like: 「ケース（scenario）問題を `{requested_count}` 問作って。」

## ローカル実行（Difyなし）
このリポジトリ内で `{contexts}` を構築し、Bedrockで問題JSONを生成して評価できる。

- 問題生成（例）:
  - `PYTHONPATH=$PWD:$PWD/src ./scripts/entry/run_question_gen.py --kb-dir s3/course_store/course_id=test_00/knowledge_md/v1/lec_仕事の基礎_00 --course-id course_id=test_00 --test-type understanding --requested-count 10 --optional-course-level beginner --out outputs/sample.json`
- 評価（MT-Bench）:
  - `./eval_system/run_eval.py --target question --input-json outputs/sample.json`
- 出力先の切替:
  - `configs/s3_sync.env` の `OUTPUT_MODE=local|s3` で制御する。

## ルーター実行（ユーザープロンプト自動判定）
ユーザー入力に応じて `summary_gen_prompt` / `question_gen_prompt` を自動判定して実行する。
```bash
./scripts/entry/run_llm_pipeline.py \
  --user-prompt "要約して" \
  --kb-dir s3/course_store/course_id=test_00/knowledge_md/v1/仕事の基礎 \
  --course-id course_id=test_00
```
例（問題生成）:
```bash
./scripts/entry/run_llm_pipeline.py \
  --user-prompt "Pythonの問題を作成して" \
  --kb-dir s3/course_store/course_id=test_00/knowledge_md/v1/言語_Python初級 \
  --course-id course_id=test_00 \
  --out outputs/python_questions.json
```
補足:
- ルーティング結果は `logs/llm_router.jsonl` に記録される。
- 強制指定: `--force-prompt-id summary_gen_prompt`
- 簡易判定を無効化: `--no-keyword-route`
- 「問題/テスト/クイズ/出題」の語が含まれると `question_gen_prompt` にルーティングされる。

## lecture_id の扱い（重要）
- 既定は **フォルダ構成から自動推定**（`knowledge_md/v1/<lecture_id>/`）。
- 本番運用では **LMS/教材管理の講義ID** に必ず置き換える。

## 現在の固定値（PoC）
- `test_genre`: comprehension 固定
- `optional_course_level`: beginner 固定
- `course_id`: course_id=test_00 固定（例）
- `lecture_id`: 例）`仕事の基礎` / `言語/Python初級`（フォルダ名から推定）
- `past_questions_string_data`: 未指定（空扱い）
- `weight_flag`: 1 / 3 / 5 固定（ジョブ別、`points` は weight_flag 連動で整数）

## 要約生成プロンプト（登録場所）
- `configs/system_prompts.json` に要約用System Promptを登録済み。

## 要約生成（summary）
- 出力先: `knowledge_md/v1/<lecture_id>/summary.json`（Markdownと同じフォルダ）
- 実行例（ローカルに保存）:
  - `./scripts/entry/run_summary_gen.py --kb-dir s3/course_store/<course_id>/knowledge_md/v1/<lecture_id> --course-id <course_id>`
- summary.json の構造:
  - フォルダ全体の要約（summary/skills）
  - items に Markdownごとの要約（source_md/source_path 付き）

### ジャンル別一括生成（理解×初級）
- `./scripts/jobs/run_question_gen_batch.sh`
  - lecture_id ごとに10問ずつ生成する。

### 難しさ別一括生成（理解×初級）
- `./scripts/jobs/run_question_gen_batch_weights.sh`
  - weight_flag を 1〜5 に固定したジョブを各lectureで実行する（各10問）。

### 停止しにくい実行（分割＋再開）
- `./scripts/jobs/run_question_gen_queue.sh`
  - 1ジョブずつ順番に実行する（既存ファイルは自動スキップ）。
  - 並列数は `configs/s3_sync.env` の `MAX_PARALLEL` で管理する。
  - 失敗時の再試行回数は `RETRY_PER_JOB` で管理する。

## question_bank 同期（Icon除外）
```bash
./scripts/sync/sync_course_store_to_s3.sh
```
※ Icon はアップロード対象外とする。

## Bedrock Knowledge Bases 取り込み
Bedrock Knowledge Bases を使う場合は、S3の反映後に取り込みを実行する。

```bash
PYTHONPATH=$PWD /Users/tadayoshi_miura/workspace/prepare/.venv_py313/bin/python \
  scripts/entry/run_kb_ingest.py --wait
```

`KB_ID` / `DATA_SOURCE_ID` は `configs/bedrock_kb.env` に保存する。

実行例（完了済み）:
- job_id: `X5QI2SEDEQ`

#### タイムアウト対策（Bedrock）
`configs/s3_sync.env` にまとめて管理する。
- `BEDROCK_READ_TIMEOUT`（例: 900）
- `BEDROCK_CONNECT_TIMEOUT`（例: 10）
- `BEDROCK_MAX_ATTEMPTS`（例: 6）
- `BEDROCK_RETRY_SLEEP`（例: 3）

## PDF（OCR→整形）の補足
- 現行パイプラインはPDFのOCR→Markdown整形まで対応済み。
- PDFを処理する場合のフロー:
  1. PDF検知 → `processed/.../extracted/pdf/` へ配置
  2. OCR（Textract等） → `processed/.../ocr/raw/` 出力
  3. 軽整形 → `processed/.../ocr/normalized/`
  4. Markdown整形 → `course_store/.../knowledge_md/v1/<lecture_id>/`

## PDF テキスト層判定の実装（補足）
- `video_pipeline/pdf_processor.py` でテキスト層の有無を判定し、テキスト層があれば抽出、なければ OCR バックエンド（差し替え可）を呼ぶ構造に変更済み。
- OCR バックエンドは未定のため、`PdfProcessor` の `ocr_backend` に実装を差し込む運用。

## CSV列マッピング（補足）
- CSVは「1ファイル=1コース」前提。`course_id` 列があれば1行目の値を採用する。
- CSVにジャンル列が無い場合があるため、列→意味の対応は `configs/csv_mapping.yml` に集約。
- ここで列名を変更しても、CSV専用の新規変数は作らず、既存の構造（セクション/パート/本文）にマッピングする。
- ジャンル判定はファイル全体（CSV全文）を対象にした推定で、行ごとに分岐しない。

## 互換用のshim
- `question_gen/` / `summary_gen/` / `rag_core/` / `shared/` は削除済み。
