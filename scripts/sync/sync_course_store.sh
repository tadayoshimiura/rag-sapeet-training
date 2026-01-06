#!/usr/bin/env bash
# course_store の同期（directionで S3→ローカル / ローカル→S3 を切替）

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/../../configs/s3_sync.env"

usage() {
  echo "Usage: $0 --direction s3_to_local|local_to_s3"
  exit 1
}

DIRECTION=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --direction)
      DIRECTION="$2"
      shift 2
      ;;
    *)
      usage
      ;;
  esac
done

if [[ -z "$DIRECTION" ]]; then
  usage
fi

# SSO ログイン（毎回実施。既に有効なら即終了）
aws sso login --profile "$AWS_PROFILE"

# 除外引数を正しく組み立てる（"--exclude" とパターンは別引数）
EXCLUDE_ARGS=()
for pattern in "${EXCLUDES[@]}"; do
  EXCLUDE_ARGS+=(--exclude "$pattern")
done

# 同期前にコース単位でローカルを圧縮バックアップ
BACKUP_ROOT="/Users/tadayoshi_miura/workspace/prepare/s3/.backups"
TS="$(date +"%Y%m%d_%H%M%S")"
COURSE_ROOT="$(cd "$(dirname "$(dirname "$KB_DEST")")" && pwd)"
mkdir -p "$BACKUP_ROOT"
if [ -d "$COURSE_ROOT" ]; then
  tar -czf "$BACKUP_ROOT/course_store_${COURSE_ID}_${TS}.tar.gz" -C "$COURSE_ROOT" .
fi

LOCAL_KB="$KB_DEST"
S3_KB="$KB_SRC"
LOCAL_QB="$(cd "$(dirname "$(dirname "$KB_DEST")")" && pwd)/question_bank"
S3_QB="s3://$BUCKET/course_store/${COURSE_ID}/question_bank"

if [[ "$DIRECTION" == "s3_to_local" ]]; then
  # summary.json はローカル正本なので削除しない
  EXCLUDE_SUMMARY=(--exclude "summary.json" --exclude "summary.json.raw*")
  echo "download: $S3_KB -> $LOCAL_KB"
  aws s3 sync "$S3_KB" "$LOCAL_KB" \
    --profile "$AWS_PROFILE" \
    --delete \
    "${EXCLUDE_ARGS[@]}" \
    "${EXCLUDE_SUMMARY[@]}"
  if [ -d "$LOCAL_QB" ]; then
    echo "download: $S3_QB -> $LOCAL_QB"
    aws s3 sync "$S3_QB" "$LOCAL_QB" \
      --profile "$AWS_PROFILE" \
      --delete \
      "${EXCLUDE_ARGS[@]}"
  fi
elif [[ "$DIRECTION" == "local_to_s3" ]]; then
  echo "upload: $LOCAL_KB -> $S3_KB"
  aws s3 sync "$LOCAL_KB" "$S3_KB" \
    --profile "$AWS_PROFILE" \
    "${EXCLUDE_ARGS[@]}"
  if [ -d "$LOCAL_QB" ]; then
    echo "upload: $LOCAL_QB -> $S3_QB"
    aws s3 sync "$LOCAL_QB" "$S3_QB" \
      --profile "$AWS_PROFILE" \
      "${EXCLUDE_ARGS[@]}"
  fi
else
  usage
fi

echo "完了"
