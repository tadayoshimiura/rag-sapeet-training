# 映像 → テキスト → RAG 前処理（最終まとめ・確定版）

## 1. 目的
- 講座一式（動画・PDF・HTML・音声・資料フォルダ混在）を人手なしでテキスト化
- RAG（Amazon Bedrock系）に最適な Markdown 正本を生成
- 並列処理・再実行・再生成に耐える実運用設計とする
- 対象は講座動画・教材のみのため、PII/セキュリティ対応は本設計のスコープ外とする

## 2. 基本方針（結論）
- 重い動画は処理しない。S3に保管のみ
- 音声に落として分割 → 並列ASR
- LLMで誤り補正＋Markdown整形
- RAGで使う正本は1箇所に固定

## 3. 全体フロー（自動化範囲）
```
講座フォルダ一式（S3アップロード）
↓
動画 → 音声抽出（ffmpeg / EKS）
↓
音声分割（5–15分）
↓
並列ASR（Whisper系 / EKS Pod）
↓
結合＋誤り補正（LLM）
↓
Markdown整形（Bedrock）
↓
RAG用テキストとして確定
```

## 4. ID命名規約（統一）
- 講座IDは `course_id=test_00` 形式に統一
- `course_id_test_00` のような表記は使用しない
- S3パス・ジョブID・メタデータはすべてこの形式に従う

## 5. S3 ディレクトリ構成（講座単位）
```
s3://bucket/
├── raw/
│   └── course_packages/
│       └── course_id=test_00/
│           └── upload/              # アップロード原本（不変）
│
├── processed/
│   └── course_id=test_00/
│       ├── extracted/               # 種別仕分け
│       │   ├── pdf/
│       │   ├── movie/
│       │   ├── audio/
│       │   └── html/
│       ├── audio/                   # 抽出・分割音声
│       ├── transcript/
│       │   ├── raw/
│       │   └── normalized/
│       └── ocr/
│           ├── raw/
│           └── normalized/
│
└── course_store/
    └── course_id=test_00/
        └── knowledge_md/
            ├── v1/                  # RAG正本（唯一参照）
            │   └── <lecture_id>/     # 講義単位（フォルダ名で講義IDを管理）
            └── v2/                  # 将来再生成用
```

## 6. 使用コンポーネント
- 実行基盤：AWS EKS
- 音声抽出・分割：ffmpeg
- ASR：Whisper / faster-whisper（並列）
- 整形・補正：LLM（Amazon Bedrock）
- Embedding：Titan Embeddings v2

## 7. 音声・分割ポリシー
- 音声フォーマット：mono / 16kHz WAV
- 分割単位：5–15分
- 無音検出を優先
- 最大長超過時は強制分割
- 分割単位が並列ASR・再実行の最小単位

## 8. LLM出力仕様（Markdown契約）
**見出しルール**
- `#` (H1)：章（講座・動画の大区切り）
- `##` (H2)：セクション
- `###` (H3)：補足・詳細

**本文ルール**
- 箇条書きは `-`
- 1段落＝1トピック

**メタ情報**
- 各段落末尾にタイムコードを付与（形式：`HH:MM:SS–HH:MM:SS`）
- 可能であれば元ファイル名を併記

例:
```
## 前処理の基本方針
- 動画は音声に変換して処理する (00:12:30–00:14:10, source=lecture01.mp4)
```

## 9. 再実行・品質管理（運用設計）
**検証フラグの配置**
```
processed/
└── course_id=test_00/
    └── transcript/
        ├── normalized/
        │   ├── chunk_001.txt
        │   ├── chunk_002.txt
        │   └── _status.json
```

`_status.json` 例:
```
{
  "asr_quality": "ok",
  "low_confidence_chunks": ["chunk_002"],
  "last_checked_at": "2025-XX-XXT12:00:00Z"
}
```
- 低品質チャンクのみ再ASR・再整形
- 再実行しても全体を壊さない設計

## 10. コスト・性能の目安（簡易）
- ASRノード例: g5.xlarge
- 同時処理: 2〜4音声 / Pod
- 並列数は「音声分割数 × Pod数」で制御
- LLM整形は非同期バッチ前提
- 詳細数値はPoC結果で調整

## 11. 正本ルール（最重要）
| 種別 | 扱い |
| --- | --- |
| raw | 原本・不変 |
| processed | 再生成OK |
| course_store/knowledge_md/v1 | RAG唯一の正本 |
| work | 実験用（参照禁止） |

## 12. 最終評価
- フロー: 明確
- 命名: 統一済み
- RAG適性: 高い
- 運用耐性: 十分

講座動画向けの全自動RAG前処理設計として、そのまま確定可能。

### ここが重要
- 動画は保管のみ、処理は音声分割・並列ASRが前提
- `course_id=test_00` に統一し、 raw → processed → course_store(v1) の一方向パイプライン
- RAGで使う正本は knowledge_md（v1）のみ
