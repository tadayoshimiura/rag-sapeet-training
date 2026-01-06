#!/usr/bin/env python3
"""Markdown から要約JSONを生成する。"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import argparse
import json
import time
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from shared.bedrock_llm import BedrockLLM
from shared.cli_settings import load_llm_pipeline_settings
from shared.contexts import build_contexts_from_markdown_dir, build_contexts_from_markdown_files, to_contexts_payload
from shared.front_matter import parse_md_meta
from pipelines.question_gen.llm_pipeline import parse_json_array_with_repair
from shared.output_utils import append_suffix, basename, is_s3_uri, write_json, write_text
from pipelines.summary_gen.prompts import build_summary_rewrite_system_prompt, build_summary_system_prompt
from pipelines.video_pipeline.lecture_map import infer_lecture_from_kb_path


def _parse_json_array_with_repair(llm: BedrockLLM, system: str, raw_text: str) -> list:
    """JSON配列として読めるまで最小限の修復を行う。"""
    return parse_json_array_with_repair(llm, system, raw_text, max_tokens=2000)


def _build_user_prompt(contexts: list[dict], variables: dict) -> str:
    """要約生成用のUser Promptを組み立てる。

    引数:
        contexts: LLMに渡すチャンク配列。
        variables: 追加で渡す変数（course_idなど）。

    戻り値:
        LLMに渡すUser Prompt文字列。

    例:
        >>> _build_user_prompt([], {"course_id": "course_id=test_00"}).splitlines()[1]
        'course_id=course_id=test_00'
    """
    lines = ["以下の入力変数に基づき、JSON配列のみを出力してください。"]
    for k, v in variables.items():
        if v is None:
            continue
        lines.append(f"{k}={v}")
    lines.append("contexts:")
    lines.append(json.dumps(contexts, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def _raw_out_base(out_path: str, raw_out_dir: str | None) -> str:
    """rawログの出力先基準パスを決める。

    引数:
        out_path: 生成結果の出力先。
        raw_out_dir: rawログの出力先ディレクトリ（省略可）。

    戻り値:
        rawログの基準パス。

    例:
        >>> _raw_out_base('a/summary.json', 'raw')
        'raw/summary.json'
    """
    if raw_out_dir:
        return f"{raw_out_dir.rstrip('/')}/{basename(out_path)}"
    return out_path


def _generate_with_retry(
    llm: BedrockLLM,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
    max_retries: int = 2,
    sleep_sec: float = 2.0,
) -> str:
    """Bedrock呼び出しをリトライ付きで実行する。

    引数:
        llm: LLMクライアント。
        system: System Prompt本文。
        user: User Prompt本文。
        max_tokens: 生成上限トークン。
        temperature: 生成温度。
        max_retries: リトライ回数。
        sleep_sec: リトライ間隔（秒）。

    戻り値:
        LLMの出力文字列。

    例:
        >>> isinstance(_generate_with_retry(llm, \"役割:\", \"入力\", 10, 0.0), str)
        True
    """
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 2):
        try:
            return llm.generate(system=system, user=user, max_tokens=max_tokens, temperature=temperature)
        except (ClientError, BotoCoreError) as e:
            last_err = e
            time.sleep(sleep_sec * attempt)
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(sleep_sec * attempt)
    raise RuntimeError(f"Bedrock呼び出しが失敗しました: {last_err}") from last_err


def _regenerate_payload(
    llm: BedrockLLM,
    system: str,
    user: str,
    raw_path: str,
    max_tokens: int,
    temperature: float,
) -> list:
    """LLMを再実行してJSON配列を取得する。

    引数:
        llm: LLMクライアント。
        system: System Prompt本文。
        user: User Prompt本文。
        raw_path: rawログの出力先パス。
        max_tokens: 生成上限トークン。
        temperature: 生成温度。

    戻り値:
        JSON配列として読み込んだPythonリスト。

    例:
        >>> isinstance(_regenerate_payload(llm, \"役割:\", \"入力\", \"raw.txt\", 200, 0.0), list)  # doctest: +SKIP
        True
    """
    text = _generate_with_retry(llm, system=system, user=user, max_tokens=max_tokens, temperature=temperature)
    write_text(raw_path, text)
    return _parse_json_array_with_repair(llm, system=system, raw_text=text)


def _build_overall_contexts(items: list[dict], max_total_chars: int | None) -> list[dict]:
    """items配列から全体要約用のcontextsを作る。

    引数:
        items: 各MDの要約オブジェクト配列。
        max_total_chars: 全体の最大文字数（上限）。

    戻り値:
        contexts形式の配列。

    例:
        >>> _build_overall_contexts([{\"summary\":\"a\"}], None)[0][\"chunk_id\"]
        'summary_0001'
    """
    contexts: list[dict] = []
    total = 0
    for idx, item in enumerate(items, start=1):
        text = str(item.get("summary", "")).strip()
        if not text:
            continue
        total += len(text)
        if max_total_chars is not None and total > max_total_chars:
            break
        ctx = {"chunk_id": f"summary_{idx:04d}", "text": text}
        source_md = item.get("source_md")
        source_path = item.get("source_path")
        if source_md or source_path:
            ctx["source"] = {"source_md": source_md, "source_path": source_path}
        contexts.append(ctx)
    return contexts


def _merge_skills(items: list[dict], max_skills: int = 8) -> list[str]:
    """items内のskillsを集計して上位を返す。

    引数:
        items: 要約オブジェクト配列。
        max_skills: 返す上限件数。

    戻り値:
        出現回数順のskills配列。

    例:
        >>> _merge_skills([{\"skills\":[\"A\",\"B\",\"A\"]}], 1)
        ['A']
    """
    counts: dict[str, int] = {}
    first_order: dict[str, int] = {}
    order = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        skills = item.get("skills") or []
        if not isinstance(skills, list):
            continue
        for s in skills:
            s_str = str(s).strip()
            if not s_str:
                continue
            counts[s_str] = counts.get(s_str, 0) + 1
            if s_str not in first_order:
                first_order[s_str] = order
                order += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], first_order.get(kv[0], 0)))
    return [k for k, _ in ranked[:max_skills]]


def _resolve_out_path(kb_dir: str | None, kb_file: str | None, out: str | None) -> str:
    """出力先を決定する。

    引数:
        kb_dir: Markdownディレクトリ。
        kb_file: Markdown単一ファイル。
        out: 明示指定の出力先。

    戻り値:
        出力先パス（summary.json）。

    例:
        >>> _resolve_out_path("/tmp/lec", None, None)
        '/tmp/lec/summary.json'
    """
    if out:
        return out
    if kb_file:
        return str(Path(kb_file).parent / "summary.json")
    if kb_dir:
        return str(Path(kb_dir) / "summary.json")
    raise SystemExit("出力先を決定できませんでした。--out を指定してください。")


def _load_summary_settings() -> dict:
    """rag_runtime_dev.json から summary 設定を読み込む。

    引数:
        なし。

    戻り値:
        要約設定の辞書。

    例:
        >>> _load_summary_settings()["summary"]["min_chars"]
        160
    """
    base = Path(__file__).resolve().parents[1]
    candidates = [
        base / "configs" / "rag_runtime_dev.json",
        base.parent / "configs" / "rag_runtime_dev.json",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if not path:
        raise FileNotFoundError("rag_runtime_dev.json が見つかりません")
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = payload.get("summary_settings")
    if not summary:
        raise KeyError("rag_runtime_dev.json に summary_settings がありません")
    return {"summary": summary}


def _build_length_fix_user(summary: str, min_chars: int, max_chars: int) -> str:
    """文字数調整用のUser Promptを組み立てる。

    引数:
        summary: 修正対象の要約文。
        min_chars: 最小文字数。
        max_chars: 最大文字数。

    戻り値:
        LLMに渡すUser Prompt文字列。

    例:
        >>> _build_length_fix_user(\"短い\", 160, 240).splitlines()[0]
        '次のsummaryを指定範囲の文字数に調整してください。'
    """
    current_len = len(summary)
    return (
        "次のsummaryを指定範囲の文字数に調整してください。\n"
        f"min_chars={min_chars}\n"
        f"max_chars={max_chars}\n"
        f"current_len={current_len}\n"
        "summary:\n"
        f"{summary}\n"
    )


def _ensure_summary_length(
    llm: BedrockLLM,
    system: str,
    summary: str,
    min_chars: int,
    max_chars: int,
    max_retries: int,
    max_tokens: int,
    temperature: float,
) -> str:
    """要約文が文字数条件に収まるまで調整する。

    引数:
        llm: LLMクライアント。
        system: 文字数調整用System Prompt。
        summary: 修正対象の要約文。
        min_chars: 最小文字数。
        max_chars: 最大文字数。
        max_retries: 調整の最大試行回数。
        max_tokens: 調整時の最大トークン。
        temperature: 調整時の温度。

    戻り値:
        文字数条件を満たした要約文。

    例:
        >>> _ensure_summary_length(llm, \"役割:\", \"短い\", 160, 240, 1, 200, 0.0)  # doctest: +SKIP
        '...'
    """
    if min_chars <= len(summary) <= max_chars:
        return summary
    user = _build_length_fix_user(summary, min_chars, max_chars)
    last = summary
    for _ in range(max_retries + 1):
        fixed_text = _generate_with_retry(llm, system=system, user=user, max_tokens=max_tokens, temperature=temperature)
        payload = _parse_json_array_with_repair(llm, system=system, raw_text=fixed_text)
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            candidate = str(payload[0].get("summary", "")).strip()
            if min_chars <= len(candidate) <= max_chars:
                return candidate
            if candidate:
                last = candidate
                user = _build_length_fix_user(candidate, min_chars, max_chars)
    raise RuntimeError(f"要約の文字数調整に失敗しました（len={len(last)}）")


def _is_summary_length_ok(summary: str, min_chars: int, max_chars: int) -> bool:
    """要約文の文字数が指定範囲内か判定する。

    引数:
        summary: 判定対象の要約文。
        min_chars: 最小文字数。
        max_chars: 最大文字数。

    戻り値:
        範囲内ならTrue、範囲外ならFalse。

    例:
        >>> _is_summary_length_ok('a' * 160, 160, 240)
        True
    """
    return min_chars <= len(summary) <= max_chars


def main() -> None:
    parser = argparse.ArgumentParser(description="講義要約のJSONを生成する（summary）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--kb-dir", help="ローカルのknowledge_mdディレクトリ（例: s3/course_store/.../knowledge_md/v1）")
    group.add_argument("--kb-file", help="単一のMarkdownファイル")
    parser.add_argument("--course-id", default=None, help="course_id=... 形式（未指定ならMarkdownのヘッダから推定）")
    parser.add_argument("--lecture-id", default=None, help="講義ID（未指定ならMarkdownのヘッダ/フォルダから推定）")
    parser.add_argument("--out", default=None, help="出力先（未指定ならMarkdownフォルダ直下の summary.json）")
    parser.add_argument("--raw-out-dir", default=None, help="rawログの出力先ディレクトリ（未指定ならoutと同じ場所）")
    parser.add_argument("--contexts-max-chars", type=int, default=None, help="contextsの1チャンク最大文字数")
    parser.add_argument("--max-md-files", type=int, default=None, help="ディレクトリ指定時に読むMarkdownファイルの最大件数")
    parser.add_argument("--max-context-chunks", type=int, default=None, help="contextsの最大チャンク数")
    parser.add_argument("--max-contexts-total-chars", type=int, default=None, help="contexts本文の合計文字数上限")
    args = parser.parse_args()

    settings = load_llm_pipeline_settings()
    ctx = settings.get("contexts", {})
    scfg = settings.get("summary_gen", {})
    common = settings.get("common", {})
    if args.contexts_max_chars is None:
        args.contexts_max_chars = int(ctx.get("max_chars_per_chunk", 1200))
    if args.max_md_files is None:
        args.max_md_files = int(scfg.get("max_md_files", 20))
    if args.max_context_chunks is None:
        args.max_context_chunks = int(ctx.get("max_chunks", 120))
    if args.max_contexts_total_chars is None:
        args.max_contexts_total_chars = int(ctx.get("max_total_chars", 24000))

    if args.kb_file:
        md_files = [Path(args.kb_file)]
    else:
        md_files = sorted(Path(args.kb_dir).rglob("*.md"))[: args.max_md_files]
    if not md_files:
        raise SystemExit("Markdownが見つかりませんでした。kb-dir / kb-file を確認してください。")

    out_path = _resolve_out_path(args.kb_dir, args.kb_file, args.out)
    settings = _load_summary_settings()
    summary_cfg = settings.get("summary", {})
    min_chars = int(summary_cfg.get("min_chars", 160))
    max_chars = int(summary_cfg.get("max_chars", 240))
    length_fix_retries = int(summary_cfg.get("length_fix_retries", 2))
    length_fix_max_tokens = int(summary_cfg.get("length_fix_max_tokens", 600))
    length_fix_temperature = float(summary_cfg.get("length_fix_temperature", 0.0))

    model_id = scfg.get("model_id") or common.get("model_id")
    region = scfg.get("region") or common.get("region")
    if not model_id:
        raise SystemExit("summary_gen の model_id が未設定です（configs/rag_runtime_dev.json の llm_models.common）")
    llm = BedrockLLM(model_id=model_id, region=region)
    system = build_summary_system_prompt()
    rewrite_system = build_summary_rewrite_system_prompt()

    summaries: list[dict] = []
    overall_meta: dict | None = None
    for md_path in md_files:
        chunks = build_contexts_from_markdown_files(
            [str(md_path)],
            max_chars_per_chunk=args.contexts_max_chars,
            max_chunks=args.max_context_chunks,
            max_total_chars=args.max_contexts_total_chars,
        )
        contexts = to_contexts_payload(chunks)

        meta = parse_md_meta(md_path.read_text(encoding="utf-8", errors="replace"))
        course_id = args.course_id or meta.course_id
        lecture_id = args.lecture_id or meta.lecture_id or infer_lecture_from_kb_path(str(md_path))
        if not course_id:
            raise SystemExit("course_id を特定できませんでした。--course-id を指定するか、Markdownヘッダに設定してください。")
        if not lecture_id:
            raise SystemExit("lecture_id を特定できませんでした。--lecture-id を指定するか、Markdownヘッダに設定してください。")
        if overall_meta is None:
            overall_meta = {"course_id": course_id, "lecture_id": lecture_id}

        user = _build_user_prompt(
            contexts=contexts,
            variables={
                "course_id": course_id,
                "lecture_id": lecture_id,
            },
        )

        raw_base = _raw_out_base(out_path, args.raw_out_dir)
        payload = _regenerate_payload(
            llm=llm,
            system=system,
            user=user,
            raw_path=append_suffix(raw_base, f".raw.{md_path.name}.txt"),
            max_tokens=2000,
            temperature=0.0,
        )
        if isinstance(payload, list) and payload:
            item = payload[0]
            if isinstance(item, dict):
                item["course_id"] = course_id
                item["lecture_id"] = lecture_id
                item["source_md"] = md_path.name
                if meta.source_path:
                    item["source_path"] = meta.source_path
                item_summary = str(item.get("summary", "")).strip()
                if not _is_summary_length_ok(item_summary, min_chars, max_chars):
                    strict_user = _build_user_prompt(
                        contexts=contexts,
                        variables={
                            "course_id": course_id,
                            "lecture_id": lecture_id,
                            "summary_length_strict": "true",
                            "summary_length_range": f"{min_chars}-{max_chars}",
                        },
                    )
                    strict_payload = _regenerate_payload(
                        llm=llm,
                        system=system,
                        user=strict_user,
                        raw_path=append_suffix(raw_base, f".raw.strict.{md_path.name}.txt"),
                        max_tokens=2000,
                        temperature=0.0,
                    )
                    if not (isinstance(strict_payload, list) and strict_payload):
                        raise RuntimeError(f"要約の再生成が空です: {md_path}") from None
                    strict_item = strict_payload[0]
                    if not isinstance(strict_item, dict):
                        raise RuntimeError(f"要約の再生成が不正です: {md_path}") from None
                    strict_item["course_id"] = course_id
                    strict_item["lecture_id"] = lecture_id
                    strict_item["source_md"] = md_path.name
                    if meta.source_path:
                        strict_item["source_path"] = meta.source_path
                    item = strict_item
                    item_summary = str(item.get("summary", "")).strip()
                try:
                    item["summary"] = _ensure_summary_length(
                        llm=llm,
                        system=rewrite_system,
                        summary=item_summary,
                        min_chars=min_chars,
                        max_chars=max_chars,
                        max_retries=length_fix_retries,
                        max_tokens=length_fix_max_tokens,
                        temperature=length_fix_temperature,
                    )
                except RuntimeError:
                    retry_payload = _regenerate_payload(
                        llm=llm,
                        system=system,
                        user=user,
                        raw_path=append_suffix(raw_base, f".raw.retry.{md_path.name}.txt"),
                        max_tokens=2000,
                        temperature=0.0,
                    )
                    if not (isinstance(retry_payload, list) and retry_payload):
                        raise RuntimeError(f"要約の再生成が空です: {md_path}") from None
                    retry_item = retry_payload[0]
                    if not isinstance(retry_item, dict):
                        raise RuntimeError(f"要約の再生成が不正です: {md_path}") from None
                    retry_item["course_id"] = course_id
                    retry_item["lecture_id"] = lecture_id
                    retry_item["source_md"] = md_path.name
                    if meta.source_path:
                        retry_item["source_path"] = meta.source_path
                    retry_summary = str(retry_item.get("summary", "")).strip()
                    retry_item["summary"] = _ensure_summary_length(
                        llm=llm,
                        system=rewrite_system,
                        summary=retry_summary,
                        min_chars=min_chars,
                        max_chars=max_chars,
                        max_retries=length_fix_retries,
                        max_tokens=length_fix_max_tokens,
                        temperature=length_fix_temperature,
                    )
                    item = retry_item
            summaries.append(item)
        else:
            raise RuntimeError(f"要約結果が空です: {md_path}")

    # フォルダ全体のまとめ要約（itemsの要約文を再要約）
    overall_contexts = _build_overall_contexts(summaries, args.max_contexts_total_chars)
    overall_user = _build_user_prompt(
        contexts=overall_contexts,
        variables={
            "course_id": (overall_meta or {}).get("course_id"),
            "lecture_id": (overall_meta or {}).get("lecture_id"),
            "summary_scope": "overall",
            "summary_instruction": "items の全要約を均等に反映し、特定の項目に偏らないこと",
        },
    )
    raw_base = _raw_out_base(out_path, args.raw_out_dir)
    overall_payload = _regenerate_payload(
        llm=llm,
        system=system,
        user=overall_user,
        raw_path=append_suffix(raw_base, ".raw.overall.txt"),
        max_tokens=2000,
        temperature=0.0,
    )
    if not (isinstance(overall_payload, list) and overall_payload):
        raise RuntimeError("フォルダ全体の要約が空です。")
    overall_item = overall_payload[0]
    if not isinstance(overall_item, dict):
        raise RuntimeError("フォルダ全体の要約が不正です。")
    overall_summary_text = str(overall_item.get("summary", "")).strip()
    if not _is_summary_length_ok(overall_summary_text, min_chars, max_chars):
        strict_overall_user = _build_user_prompt(
            contexts=overall_contexts,
            variables={
                "course_id": (overall_meta or {}).get("course_id"),
                "lecture_id": (overall_meta or {}).get("lecture_id"),
                "summary_length_strict": "true",
                "summary_length_range": f"{min_chars}-{max_chars}",
                "summary_scope": "overall",
                "summary_instruction": "items の全要約を均等に反映し、特定の項目に偏らないこと",
            },
        )
        strict_overall_payload = _regenerate_payload(
            llm=llm,
            system=system,
            user=strict_overall_user,
            raw_path=append_suffix(raw_base, ".raw.strict.overall.txt"),
            max_tokens=2000,
            temperature=0.0,
        )
        if not (isinstance(strict_overall_payload, list) and strict_overall_payload):
            raise RuntimeError("フォルダ全体の要約が空です（厳格再生成）。") from None
        strict_overall_item = strict_overall_payload[0]
        if not isinstance(strict_overall_item, dict):
            raise RuntimeError("フォルダ全体の要約が不正です（厳格再生成）。") from None
        overall_summary_text = str(strict_overall_item.get("summary", "")).strip()
    try:
        overall_summary = _ensure_summary_length(
            llm=llm,
            system=rewrite_system,
            summary=overall_summary_text,
            min_chars=min_chars,
            max_chars=max_chars,
            max_retries=length_fix_retries,
            max_tokens=length_fix_max_tokens,
            temperature=length_fix_temperature,
        )
    except RuntimeError:
        retry_overall_payload = _regenerate_payload(
            llm=llm,
            system=system,
            user=overall_user,
            raw_path=append_suffix(raw_base, ".raw.retry.overall.txt"),
            max_tokens=2000,
            temperature=0.0,
        )
        if not (isinstance(retry_overall_payload, list) and retry_overall_payload):
            raise RuntimeError("フォルダ全体の要約が空です（再生成）。") from None
        retry_overall_item = retry_overall_payload[0]
        if not isinstance(retry_overall_item, dict):
            raise RuntimeError("フォルダ全体の要約が不正です（再生成）。") from None
        overall_summary = _ensure_summary_length(
            llm=llm,
            system=rewrite_system,
            summary=str(retry_overall_item.get("summary", "")).strip(),
            min_chars=min_chars,
            max_chars=max_chars,
            max_retries=length_fix_retries,
            max_tokens=length_fix_max_tokens,
            temperature=length_fix_temperature,
        )

    output = {
        "course_id": (overall_meta or {}).get("course_id"),
        "lecture_id": (overall_meta or {}).get("lecture_id"),
        "summary": overall_summary,
        "items": summaries,
    }

    write_json(out_path, output)


if __name__ == "__main__":
    main()
