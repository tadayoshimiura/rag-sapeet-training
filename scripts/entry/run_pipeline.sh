#!/usr/bin/env bash
# 1コマンドで「upload同期→差分だけ処理」まで実行する。

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${ROOT_DIR}/configs/s3_sync.env"

MAX_RETRIES="${RUN_PIPELINE_MAX_RETRIES:-2}"
RETRY_SLEEP="${RUN_PIPELINE_RETRY_SLEEP:-5}"

attempt=0
while true; do
  attempt=$((attempt + 1))
  echo "run_pipeline: attempt ${attempt}/${MAX_RETRIES}"

  # 同期（差分だけアップロードされる）
  "${SCRIPT_DIR}/../sync/sync_upload.sh"

  # 処理（差分だけ実行）
  PYTHONPATH="$ROOT_DIR:$ROOT_DIR/src" \
  AWS_PROFILE="$AWS_PROFILE" \
  AWS_REGION="$AWS_REGION" \
  AWS_DEFAULT_REGION="$AWS_DEFAULT_REGION" \
  "$PYTHON_BIN" "${SCRIPT_DIR}/run_course_pipeline.py" \
    --bucket "$BUCKET" \
    --course-id "$COURSE_ID" \
    --only-changed && break

  if [ "$attempt" -ge "$MAX_RETRIES" ]; then
    echo "run_pipeline: failed after ${attempt} attempts"
    exit 1
  fi
  echo "run_pipeline: retry in ${RETRY_SLEEP}s"
  sleep "$RETRY_SLEEP"
done
