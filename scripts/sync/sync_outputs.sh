#!/usr/bin/env bash
# S3（出力側）→ ローカル（s3/ミラー）を同期する。
# 対象:
# - course_store（knowledge_md / question_bank）
# - processed/_status.json（差分処理の状態）

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/../../configs/s3_sync.env"

"${SCRIPT_DIR}/sync_course_store.sh" --direction s3_to_local

echo "download: $STATUS_SRC -> $STATUS_DEST"
mkdir -p "$(dirname "$STATUS_DEST")"
aws s3 cp "$STATUS_SRC" "$STATUS_DEST" --profile "$AWS_PROFILE" || true

# aws s3 sync は空ディレクトリを消さないため、不要な空フォルダを掃除する
find "$KB_DEST" -type d -empty -delete || true

echo "完了"
