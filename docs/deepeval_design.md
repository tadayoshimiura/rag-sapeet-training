# DeepEval 運用設計（改造点の説明用）

## 目的
- 既存の `question_bank` / `summary.json` を **変換なしで評価**できるようにする。
- 評価LLMは **Amazon Bedrock** を使用する（OpenAI不要）。
- 設定・パス指定だけで回せる最小の運用手順を提供する。

## 変更範囲（改造点）
### 1) 実行ランナー
**ファイル**: `eval_system/run_deepeval.py`  
**理由**: DeepEval標準入力と既存データ形式が異なるため、入力マッピングが必要。

主な改造点:
- **入力マッピング**
- `question_bank` 形式: `question_text/options/is_correct/evidence.quote` → `input/actual_output/context`
  - `summary.json` 形式: `items[*].summary` → `actual_output`、対応する `source_md` を `context` に採用
- **Bedrock指定**
  - `AmazonBedrockModel` を評価LLMとして使用
  - モデルとリージョンは環境変数から取得
- **レート制御**
  - `--max-concurrent` / `--throttle-ms` で同時実行数と間隔を調整
- **レポート出力**
  - JSON/Markdown の簡易レポートを `reports/` 配下に保存

### 2) 依存関係
**ファイル**: `eval_system/requirements.txt`  
**理由**: Bedrock評価に必要な依存を隔離環境にのみ追加するため。

### 3) 手順メモ
**ファイル**: `docs/operations_notes.md`  
**理由**: 使い方・必要な環境変数を明文化するため。

## 運用設定（変更不要の前提）
- ルーブリック: DeepEval標準（デフォルト）
- モデル指定: `AWS_BEDROCK_MODEL_NAME` / `AWS_BEDROCK_REGION`
- 評価対象パス: `--input-json` で指定

## 実行例
```bash
eval_system/.venv/bin/python eval_system/run_deepeval.py \
  --input-json /path/to/question_bank \
  --max-concurrent 2 \
  --throttle-ms 200 \
  --no-faithfulness
```

## 変更しない方針
- ルーブリックは当面デフォルトを利用（カスタム化は必要時のみ）
- 本体コードへの変更は極力増やさない（入力・設定で吸収）
