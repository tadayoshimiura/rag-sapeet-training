#!/usr/bin/env bash
# ローカル upload → S3 upload を固定パスで同期するラッパー
# 1) プロファイルを固定して SSO ログイン
# 2) 差分チェック（必要なら表示）
# 3) 除外ルール付きで aws s3 sync

set -euo pipefail

# 使い方:
#   ./scripts/sync/sync_upload.sh           # 差分を表示→同期
#   ./scripts/sync/sync_upload.sh --check   # 差分だけ表示（同期しない）

# 設定読み込み
SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/../../configs/s3_sync.env"

# SSO ログイン（毎回実施。既に有効なら即終了）
aws sso login --profile "$AWS_PROFILE"

# 除外引数を正しく組み立てる（"--exclude" とパターンは別引数）
EXCLUDE_ARGS=()
for pattern in "${EXCLUDES[@]}"; do
  EXCLUDE_ARGS+=(--exclude "$pattern")
done

MODE="sync"
if [[ "${1:-}" == "--check" ]]; then
  MODE="check"
fi

TMP_DIFF="$(mktemp)"
trap 'rm -f "$TMP_DIFF"' EXIT

aws s3 sync "$SRC" "$DEST" \
  --profile "$AWS_PROFILE" \
  "${EXCLUDE_ARGS[@]}" \
  --dryrun >"$TMP_DIFF" || true

if [[ ! -s "$TMP_DIFF" ]]; then
  echo "差分なし（ローカルuploadとS3 uploadは同一）"
  if [[ "$MODE" == "check" ]]; then
    exit 0
  fi
else
  echo "差分あり（同期対象）:"
  cat "$TMP_DIFF"
  if [[ "$MODE" == "check" ]]; then
    exit 0
  fi
fi

# 同期実行（差分がある時だけ実体がアップロードされる）
aws s3 sync "$SRC" "$DEST" \
  --profile "$AWS_PROFILE" \
  "${EXCLUDE_ARGS[@]}"
