#!/usr/bin/env python3
"""Markdown から {contexts} を生成し問題JSONを作成する。"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import argparse
from pathlib import Path

from shared.bedrock_llm import BedrockLLM
from shared.cli_settings import load_llm_pipeline_settings
from shared.contexts import build_contexts_from_markdown_dir, build_contexts_from_markdown_files, to_contexts_payload
from pipelines.question_gen.prompts import build_system_prompt, build_user_prompt
from shared.front_matter import parse_md_meta
from pipelines.question_gen.llm_pipeline import generate_json_array, strict_json_hint
from shared.output_utils import basename, is_s3_uri, write_json
from pipelines.video_pipeline.lecture_map import infer_lecture_from_kb_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Markdown（course_store）から {contexts} を作り、問題JSONを生成する")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--kb-dir", help="ローカルのMarkdownディレクトリ（例: s3/course_store/.../knowledge_md/v1）")
    group.add_argument("--kb-file", help="単一のMarkdownファイル（contextsを最小にしたいとき）")
    parser.add_argument("--course-id", default=None, help="course_id=... 形式（未指定ならMarkdownのヘッダから推定）")
    parser.add_argument("--lecture-id", default=None, help="講義ID（未指定ならMarkdownのヘッダ/フォルダから推定）")
    test_group = parser.add_mutually_exclusive_group(required=True)
    test_group.add_argument("--test-genre", choices=["comprehension", "skill", "followup"], help="Aurora準拠のテストジャンル")
    test_group.add_argument("--test-type", choices=["skill", "understanding", "retention"], help="互換用（test_genreへ変換）")
    parser.add_argument("--requested-count", type=int, required=True)
    parser.add_argument("--optional-course-level", required=True, choices=["beginner", "intermediate", "advanced"])
    parser.add_argument("--past-prompts", default=None, help="既出prompt（1行=1問）ファイル。未指定なら空。")
    parser.add_argument("--instruction", default=None, help="ジャンル指定などの追加命令（例: 初級Pythonの問題を作成せよ）。")
    parser.add_argument("--judge-model-id", default=None)
    parser.add_argument("--judge-region", default=None)
    parser.add_argument("--out", required=True, help="出力JSONパス")
    parser.add_argument("--raw-out-dir", default=None, help="rawログの出力先ディレクトリ（未指定ならoutと同じ場所）")
    parser.add_argument("--contexts-max-chars", type=int, default=None, help="contextsの1チャンク最大文字数")
    parser.add_argument("--max-md-files", type=int, default=None, help="ディレクトリ指定時に読むMarkdownファイルの最大件数")
    parser.add_argument("--max-context-chunks", type=int, default=None, help="contextsの最大チャンク数")
    parser.add_argument("--max-contexts-total-chars", type=int, default=None, help="contexts本文の合計文字数上限（超えたら末尾を削る）")
    args = parser.parse_args()

    settings = load_llm_pipeline_settings()
    ctx = settings.get("contexts", {})
    qcfg = settings.get("question_gen", {})
    common = settings.get("common", {})
    if args.contexts_max_chars is None:
        args.contexts_max_chars = int(ctx.get("max_chars_per_chunk", 1200))
    if args.max_md_files is None:
        args.max_md_files = int(qcfg.get("max_md_files", 3))
    if args.max_context_chunks is None:
        args.max_context_chunks = int(ctx.get("max_chunks", 80))
    if args.max_contexts_total_chars is None:
        args.max_contexts_total_chars = int(ctx.get("max_total_chars", 25000))

    past = Path(args.past_prompts).read_text(encoding="utf-8") if args.past_prompts else ""

    sample_path = None
    if args.kb_file:
        sample_path = Path(args.kb_file)
    else:
        md_candidates = sorted(Path(args.kb_dir).rglob("*.md"))
        sample_path = md_candidates[0] if md_candidates else None
    if sample_path is None:
        raise SystemExit("Markdownが見つかりませんでした。kb-dir / kb-file を確認してください。")

    meta = parse_md_meta(sample_path.read_text(encoding="utf-8", errors="replace"))
    course_id = args.course_id or meta.course_id
    lecture_id = args.lecture_id or meta.lecture_id or infer_lecture_from_kb_path(str(sample_path))
    if not course_id:
        raise SystemExit("course_id を特定できませんでした。--course-id を指定するか、Markdownヘッダに設定してください。")
    if not lecture_id:
        raise SystemExit("lecture_id を特定できませんでした。--lecture-id を指定するか、Markdownヘッダに設定してください。")

    if args.kb_file:
        chunks = build_contexts_from_markdown_files(
            [args.kb_file],
            max_chars_per_chunk=args.contexts_max_chars,
            max_chunks=args.max_context_chunks,
            max_total_chars=args.max_contexts_total_chars,
        )
    else:
        chunks = build_contexts_from_markdown_dir(
            args.kb_dir,
            max_chars_per_chunk=args.contexts_max_chars,
            max_files=args.max_md_files,
            max_chunks=args.max_context_chunks,
            max_total_chars=args.max_contexts_total_chars,
        )
    contexts = to_contexts_payload(chunks)

    test_genre = args.test_genre
    if not test_genre:
        mapping = {"understanding": "comprehension", "retention": "followup", "skill": "skill"}
        test_genre = mapping[args.test_type]

    system = build_system_prompt()
    user = build_user_prompt(
        contexts=contexts,
        course_id=course_id,
        lecture_id=lecture_id,
        test_genre=test_genre,
        requested_count=args.requested_count,
        optional_course_level=args.optional_course_level,
        past_questions_string_data=past,
        tbd={},
    )
    if args.instruction:
        user = user + "\n追加命令:\n" + args.instruction.strip() + "\n"

    model_id = args.judge_model_id or qcfg.get("model_id")
    region = args.judge_region or qcfg.get("region")
    if not model_id:
        raise SystemExit("question_gen の model_id が未設定です（configs/rag_runtime_dev.json の llm_models.common か --judge-model-id）")
    llm = BedrockLLM(model_id=model_id, region=region)
    out_path = Path(args.out)
    if not is_s3_uri(args.out):
        out_path.parent.mkdir(parents=True, exist_ok=True)

    raw_base = args.out
    if args.raw_out_dir:
        raw_base = f"{args.raw_out_dir.rstrip('/')}/{basename(args.out)}"
    payload = generate_json_array(
        llm,
        system,
        user,
        raw_base=raw_base,
        raw_suffix="raw",
        max_tokens=4000,
        temperature=0.0,
        attempts=3,
    )

    # requested_count を満たさない場合は、不足分だけ追加生成して埋める
    if isinstance(payload, list) and len(payload) < args.requested_count:
        existing_prompts = [str(q.get("question_text", "")).strip() for q in payload if isinstance(q, dict)]
        past_plus = (past + "\n" if past else "") + "\n".join([p for p in existing_prompts if p])
        missing = args.requested_count - len(payload)
        user2 = build_user_prompt(
            contexts=contexts,
            course_id=course_id,
            lecture_id=lecture_id,
            test_genre=test_genre,
            requested_count=missing,
            optional_course_level=args.optional_course_level,
            past_questions_string_data=past_plus,
            tbd={},
        ) + "\n不足分だけ追加で生成してください。出力はJSON配列のみ。\n" + strict_json_hint()

        payload2 = generate_json_array(
            llm,
            system,
            user2,
            raw_base=raw_base,
            raw_suffix="raw_add",
            max_tokens=4000,
            temperature=0.0,
            attempts=3,
        )
        if isinstance(payload2, list):
            payload = payload + payload2

    # 多すぎる場合は先頭から切る（運用上は requested_count を優先）
    if isinstance(payload, list) and len(payload) > args.requested_count:
        payload = payload[: args.requested_count]

    write_json(args.out, payload)


if __name__ == "__main__":
    main()
