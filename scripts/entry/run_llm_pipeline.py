#!/usr/bin/env python3
"""ユーザープロンプトから実行対象を判定してパイプラインを起動する。"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import argparse
import json
import subprocess
from pathlib import Path

from dotenv import load_dotenv, find_dotenv

from shared.bedrock_llm import BedrockLLM
from shared.prompt_store import load_system_prompt


def _detect_prompt_id(llm: BedrockLLM, user_prompt: str) -> str:
    """ユーザープロンプトから実行対象のSystem Prompt IDを判定する。

    引数:
        llm: LLMクライアント。
        user_prompt: ユーザー入力文。

    戻り値:
        System Prompt ID（例: "summary_gen_prompt"）。

    例:
        >>> _detect_prompt_id(llm, "要約して")  # doctest: +SKIP
        'summary_gen_prompt'
    """
    system = load_system_prompt("router_prompt")
    text = llm.generate(system=system, user=user_prompt, max_tokens=50, temperature=0.0)
    return text.strip().strip("\"'")


def _simple_keyword_route(user_prompt: str) -> str | None:
    """簡易キーワード判定でprompt_idを返す（該当なしはNone）。

    引数:
        user_prompt: ユーザー入力文。

    戻り値:
        prompt_id もしくは None。

    例:
        >>> _simple_keyword_route("要約して")
        'summary_gen_prompt'
    """
    text = user_prompt.lower()
    summary_keys = ("要約", "まとめ", "概要", "サマリ", "summary")
    question_keys = ("問題", "テスト", "クイズ", "出題", "question", "python")
    if any(k in text for k in summary_keys):
        return "summary_gen_prompt"
    if any(k in text for k in question_keys):
        return "question_gen_prompt"
    return None


def _log_route(path: str, payload: dict) -> None:
    """ルーティング結果をJSONLで追記する。

    引数:
        path: ログファイルパス。
        payload: 追記する内容。

    戻り値:
        なし。

    例:
        >>> _log_route("router.log", {"prompt_id": "summary_gen_prompt"})  # doctest: +SKIP
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _build_question_cmd(args: argparse.Namespace) -> list[str]:
    if not args.out:
        raise SystemExit("question_gen を実行するには --out が必要です。")
    python_bin = sys.executable
    test_genre = args.test_genre
    if not test_genre:
        mapping = {"understanding": "comprehension", "retention": "followup", "skill": "skill"}
        if not args.test_type:
            raise SystemExit("question_gen を実行するには --test-genre または --test-type が必要です。")
        test_genre = mapping[args.test_type]
    cmd = [
        python_bin,
        str(Path(__file__).resolve().parent / "run_question_gen.py"),
        "--course-id",
        args.course_id,
        "--test-genre",
        test_genre,
        "--requested-count",
        str(args.requested_count),
        "--optional-course-level",
        args.optional_course_level,
        "--out",
        args.out,
        "--max-context-chunks",
        str(args.max_context_chunks),
        "--max-contexts-total-chars",
        str(args.max_contexts_total_chars),
        "--max-md-files",
        str(args.max_md_files),
    ]
    if args.kb_dir:
        cmd += ["--kb-dir", args.kb_dir]
    if args.kb_file:
        cmd += ["--kb-file", args.kb_file]
    if args.lecture_id:
        cmd += ["--lecture-id", args.lecture_id]
    if args.past_prompts:
        cmd += ["--past-prompts", args.past_prompts]
    if args.instruction:
        cmd += ["--instruction", args.instruction]
    if args.raw_out_dir:
        cmd += ["--raw-out-dir", args.raw_out_dir]
    return cmd


def _build_summary_cmd(args: argparse.Namespace) -> list[str]:
    python_bin = sys.executable
    cmd = [
        python_bin,
        str(Path(__file__).resolve().parent / "run_summary_gen.py"),
        "--course-id",
        args.course_id,
        "--max-context-chunks",
        str(args.max_context_chunks),
        "--max-contexts-total-chars",
        str(args.max_contexts_total_chars),
        "--max-md-files",
        str(args.max_md_files),
    ]
    if args.kb_dir:
        cmd += ["--kb-dir", args.kb_dir]
    if args.kb_file:
        cmd += ["--kb-file", args.kb_file]
    if args.lecture_id:
        cmd += ["--lecture-id", args.lecture_id]
    if args.out:
        cmd += ["--out", args.out]
    if args.raw_out_dir:
        cmd += ["--raw-out-dir", args.raw_out_dir]
    return cmd


def main() -> None:
    load_dotenv(find_dotenv())
    parser = argparse.ArgumentParser(description="ユーザープロンプトを判定して要約/問題生成を自動実行する")
    parser.add_argument("--user-prompt", required=True, help="ユーザープロンプト（例: 要約して/問題を作って）")
    parser.add_argument("--kb-dir", default=None, help="Markdownディレクトリ")
    parser.add_argument("--kb-file", default=None, help="単一Markdownファイル")
    parser.add_argument("--course-id", required=True, help="course_id=... 形式")
    parser.add_argument("--lecture-id", default=None, help="講義ID（未指定なら推定）")
    parser.add_argument("--out", default=None, help="出力先（question_genは必須）")
    parser.add_argument("--test-genre", default=None, choices=["comprehension", "skill", "followup"], help="Aurora準拠のテストジャンル")
    parser.add_argument("--test-type", default=None, choices=["skill", "understanding", "retention"], help="互換用（test_genreへ変換）")
    parser.add_argument("--raw-out-dir", default=None, help="rawログの出力先")
    parser.add_argument("--max-md-files", type=int, default=20, help="読むMarkdownファイル数の上限")
    parser.add_argument("--max-context-chunks", type=int, default=120, help="contextsの最大チャンク数")
    parser.add_argument("--max-contexts-total-chars", type=int, default=24000, help="contexts本文の合計文字数上限")
    parser.add_argument("--test-type", default="understanding", choices=["skill", "understanding", "retention"])
    parser.add_argument("--requested-count", type=int, default=10)
    parser.add_argument("--optional-course-level", default="beginner", choices=["beginner", "intermediate", "advanced"])
    parser.add_argument("--past-prompts", default=None, help="既出prompt（1行=1問）ファイル")
    parser.add_argument("--instruction", default=None, help="追加命令（ジャンル指定など）")
    parser.add_argument("--router-model-id", default="anthropic.claude-3-5-sonnet-20240620-v1:0")
    parser.add_argument("--router-region", default=None)
    parser.add_argument("--force-prompt-id", default=None, help="判定を使わず指定のPrompt IDで固定する")
    parser.add_argument("--route-log", default="logs/llm_router.jsonl", help="ルーティング結果ログ(JSONL)")
    parser.add_argument("--no-keyword-route", action="store_true", help="簡易キーワード判定を無効化する")
    args = parser.parse_args()

    if not args.kb_dir and not args.kb_file:
        raise SystemExit("--kb-dir か --kb-file のどちらかを指定してください。")

    llm = BedrockLLM(model_id=args.router_model_id, region=args.router_region)
    prompt_id = args.force_prompt_id
    route_source = "forced"
    if not prompt_id:
        if not args.no_keyword_route:
            prompt_id = _simple_keyword_route(args.user_prompt)
            if prompt_id:
                route_source = "keyword"
    if not prompt_id:
        prompt_id = _detect_prompt_id(llm, args.user_prompt)
        route_source = "llm"
    prompt_id = prompt_id.strip()
    if prompt_id not in {"question_gen_prompt", "summary_gen_prompt"}:
        raise SystemExit(f"判定結果が不正です: {prompt_id}")

    _log_route(
        args.route_log,
        {
            "user_prompt": args.user_prompt,
            "prompt_id": prompt_id,
            "source": route_source,
        },
    )

    if prompt_id == "question_gen_prompt":
        cmd = _build_question_cmd(args)
    else:
        cmd = _build_summary_cmd(args)

    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
