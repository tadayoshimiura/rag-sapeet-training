#!/usr/bin/env bash
# 問題生成をバッチで実行する。
set -euo pipefail

# 事前に configs/s3_sync.env を読み込み、同じ設定で実行する
source "$(dirname "$0")/../../configs/s3_sync.env"

export AWS_PROFILE
export AWS_REGION
export AWS_DEFAULT_REGION

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/src"
PY="$PYTHON_BIN"

RUNS_DIR="$ROOT_DIR/outputs"
mkdir -p "$RUNS_DIR"
QB_DIR_LOCAL="$ROOT_DIR/s3/course_store/${COURSE_ID}/question_bank"
QB_DIR_S3="s3://$BUCKET/course_store/${COURSE_ID}/question_bank"
OUTPUT_MODE="${OUTPUT_MODE:-local}"

TEST_TYPE="understanding"
COURSE_LEVEL="beginner"

MAX_MD_FILES=20
MAX_CHUNKS=120
MAX_TOTAL_CHARS=24000

# タイムアウト対策（必要に応じて調整）
# BEDROCK_* は configs/s3_sync.env で管理する

run_one() {
  local kb_dir="$1"
  local lecture_id="$2"
  local instruction="$3"
  local out_name="$4"
  local out_path="$RUNS_DIR/$out_name"
  local raw_dir="${out_path%/*}"
  if [ "$OUTPUT_MODE" = "s3" ]; then
    out_path="$QB_DIR_S3/generated/$TEST_TYPE/$COURSE_LEVEL/$lecture_id/weight1/$out_name"
    raw_dir="${out_path%/*}"
  else
    if [ -s "$out_path" ]; then
      echo "skip (exists): $out_path"
      return 0
    fi
  fi
  local cmd=(
    "$PY" "$ROOT_DIR/scripts/entry/run_question_gen.py"
    --kb-dir "$kb_dir"
    --course-id "$COURSE_ID"
    --test-type "$TEST_TYPE"
    --requested-count 10
    --optional-course-level "$COURSE_LEVEL"
    --max-md-files "$MAX_MD_FILES"
    --max-context-chunks "$MAX_CHUNKS"
    --max-contexts-total-chars "$MAX_TOTAL_CHARS"
    --instruction "$instruction"
    --out "$out_path"
    --raw-out-dir "$raw_dir"
  )
  if [ -n "$lecture_id" ]; then
    cmd+=(--lecture-id "$lecture_id")
  fi
  "${cmd[@]}"
}

run_one_file() {
  local kb_file="$1"
  local lecture_id="$2"
  local instruction="$3"
  local out_name="$4"
  local out_path="$RUNS_DIR/$out_name"
  local raw_dir="${out_path%/*}"
  if [ "$OUTPUT_MODE" = "s3" ]; then
    out_path="$QB_DIR_S3/generated/$TEST_TYPE/$COURSE_LEVEL/$lecture_id/weight1/$out_name"
    raw_dir="${out_path%/*}"
  else
    if [ -s "$out_path" ]; then
      echo "skip (exists): $out_path"
      return 0
    fi
  fi
  local cmd=(
    "$PY" "$ROOT_DIR/scripts/entry/run_question_gen.py"
    --kb-file "$kb_file"
    --course-id "$COURSE_ID"
    --test-type "$TEST_TYPE"
    --requested-count 10
    --optional-course-level "$COURSE_LEVEL"
    --max-context-chunks "$MAX_CHUNKS"
    --max-contexts-total-chars "$MAX_TOTAL_CHARS"
    --instruction "$instruction"
    --out "$out_path"
    --raw-out-dir "$raw_dir"
  )
  if [ -n "$lecture_id" ]; then
    cmd+=(--lecture-id "$lecture_id")
  fi
  "${cmd[@]}"
}

# lecture folders
run_one "$ROOT_DIR/s3/course_store/course_id=test_00/knowledge_md/v1/lec_ビジネスモデル_00" "" "ビジネスモデルの問題を作成せよ。" "lec_ビジネスモデル_00_understanding_beginner_n10.json"
run_one "$ROOT_DIR/s3/course_store/course_id=test_00/knowledge_md/v1/lec_仕事の基礎_00" "" "仕事の基礎の問題を作成せよ。" "lec_仕事の基礎_00_understanding_beginner_n10.json"
run_one "$ROOT_DIR/s3/course_store/course_id=test_00/knowledge_md/v1/lec_Python初級_00" "" "初級Pythonの問題を作成せよ。" "lec_Python初級_00_understanding_beginner_n10.json"
run_one "$ROOT_DIR/s3/course_store/course_id=test_00/knowledge_md/v1/lec_ビジネス資格_00" "" "ビジネス資格の問題を作成せよ。" "lec_ビジネス資格_00_understanding_beginner_n10.json"
run_one "$ROOT_DIR/s3/course_store/course_id=test_00/knowledge_md/v1/lec_IT初級_00" "" "IT初級の問題を作成せよ。" "lec_IT初級_00_understanding_beginner_n10.json"
run_one "$ROOT_DIR/s3/course_store/course_id=test_00/knowledge_md/v1/lec_Ruby_00" "" "Rubyの問題を作成せよ。" "lec_Ruby_00_understanding_beginner_n10.json"
