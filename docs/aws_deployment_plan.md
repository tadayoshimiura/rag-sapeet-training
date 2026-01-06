# AWS実装の整理（ECS想定）

## 目的
- ローカルPoCからクラウド運用へ移行できるように、必要なAWS構成と作業を整理する。

## 実行基盤
- ECS/Fargate を想定（イメージはECRに保存）。

## ログ/監視
- CloudWatch Logs を標準化。
- 実行メトリクスは CloudWatch Metrics に送る。

## ジョブ制御
- Step Functions もしくは SQS で並列/リトライを制御。
- チャンク単位の再実行を前提にする。

## 認証/権限
- IAMロールを最小権限で設計。
- S3、Bedrock、OCR、ログへのアクセスは明示的に付与。

## 保存先（S3）
- raw / processed / knowledge_md / question_bank / summary を正本として運用。

## モデル方針
- 可能な限り Bedrock を利用。
- ASRは将来 Whisper依存を外す方向で検討（Bedrock/Transcribe等）。

## OCR
- Textract を想定（バックエンド差し替え可能）。

## 評価
- 現行は eval_system（LLMジャッジ）。
- 次回は OpenCompass 移行予定。

## 同期方針
- PoCはローカル作成 → 明示的にS3同期。
- 本番はS3完結（ローカル同期不要）。
