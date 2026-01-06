"""Markdown整形。"""
import os
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, List, Optional

import boto3
import botocore.exceptions

from .config import PipelineConfig
from .layout import Layout
from .s3_utils import parse_s3_uri
from .s3_utils import S3Client


class MarkdownFormatter:
    """Bedrock Claude を用いてMarkdown整形し、course_store配下に書き出す。"""

    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self.layout = Layout(cfg=cfg)
        self.s3 = S3Client(bucket=cfg.bucket)
        region = cfg.bedrock_region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
        if not region:
            raise ValueError("Bedrockリージョンが未設定です。bedrock_region か AWS_REGION を指定してください。")
        self.client = boto3.client("bedrock-runtime", region_name=region)

    def format(
        self,
        normalized_uri: str,
        source: str = "mv",
        lecture_id: str | None = None,
        dest_name: str | None = None,
        meta_category: str | None = None,
        source_uri: str | None = None,
    ) -> str:
        """正規化済みテキストをMarkdown化し、course_store配下に配置する。

        Args:
            normalized_uri: transcript/normalized/ 配下の入力テキストURI。
            source: 出自を示すキー（mv/pdf/audio/html/csv など）。
            lecture_id: 出力先の講義ID。未指定なら既定の場所に出力する。
            dest_name: 出力ファイル名（例: video123.md）。未指定なら normalized のstemを利用。
            meta_category: Markdownヘッダに入れる論理カテゴリ。未指定なら default_logical_category。
            source_uri: 元データのS3 URI（メタ情報ヘッダに埋め込む）。

        Returns:
            course_store/<course_id>/knowledge_md/v1/<lecture_id>/ に出力するMarkdownのS3 URI。
        """
        result = self.format_batch(
            [normalized_uri],
            source=source,
            lecture_id=lecture_id,
            dest_name=dest_name,
            meta_category=meta_category,
            source_uri=source_uri,
        )
        return result[0]

    def format_batch(
        self,
        normalized_uris: Iterable[str],
        source: str,
        lecture_id: str | None = None,
        dest_name: str | None = None,
        meta_category: str | None = None,
        source_uri: str | None = None,
    ) -> List[str]:
        """複数の正規化テキストを並列でMarkdown化する。"""
        uris = list(normalized_uris)
        outputs: List[str] = []

        def _process(uri: str) -> str:
            base = (dest_name or Path(uri).stem) + ".md"
            dest_root = self.layout.kb_markdown_v1_for_lecture(lecture_id or "")
            dest = dest_root + base
            with self.s3.temp_local_copy(uri) as local_path:
                with open(local_path, "r", encoding="utf-8") as f:
                    text = f.read()
            markdown = self._format_with_chunking(text, source=source, title=Path(uri).stem)
            markdown = self._prepend_metadata(
                markdown,
                category=meta_category,
                source=source,
                source_uri=source_uri,
                lecture_id=lecture_id,
            )
            with tempfile.NamedTemporaryFile(delete=False, suffix=".md") as tmp:
                tmp_path = tmp.name
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write(markdown.strip() + "\n")
                self.s3.upload_file(tmp_path, dest)
            finally:
                try:
                    os.remove(tmp_path)
                except FileNotFoundError:
                    pass
            return dest

        with ThreadPoolExecutor(max_workers=self.cfg.bedrock_max_workers) as ex:
            futures = [ex.submit(_process, uri) for uri in uris]
            for fut in as_completed(futures):
                outputs.append(fut.result())
        return outputs

    def _format_with_chunking(self, text: str, source: str, title: str) -> str:
        """長文を分割し、Claude入力上限を避けながらMarkdown化する。"""
        chunks = self._split_for_bedrock(text, limit=self.cfg.bedrock_chunk_chars)
        md_parts: List[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            chunk_title = title if len(chunks) == 1 else f"{title}-part{idx}"
            md = self._call_bedrock_with_retry(chunk, source=source, title=chunk_title)
            md_parts.append(md.strip())
        return "\n\n".join(md_parts)

    def _split_for_bedrock(self, text: str, limit: int) -> List[str]:
        """段落単位で分割し、limit超過を防ぐ。超える場合は強制スライス。"""
        if len(text) <= limit:
            return [text]
        paras = text.replace("\r\n", "\n").split("\n\n")
        out: List[str] = []
        buf: List[str] = []
        count = 0
        for para in paras:
            plen = len(para)
            # 単一段落が極端に長い場合は直接スライス
            if plen > limit:
                if buf:
                    out.append("\n\n".join(buf))
                    buf = []
                    count = 0
                start = 0
                while start < plen:
                    out.append(para[start : start + limit])
                    start += limit
                continue
            if count + plen + (2 if buf else 0) > limit:
                out.append("\n\n".join(buf))
                buf = [para]
                count = plen
            else:
                buf.append(para)
                count += plen + (2 if buf[:-1] else 0)
        if buf:
            out.append("\n\n".join(buf))
        return [chunk for chunk in out if chunk.strip()]

    def _call_bedrock_with_retry(self, transcript: str, source: str, title: str) -> str:
        """リトライ付きでBedrockに投げる。"""
        last_err: Exception | None = None
        for attempt in range(1, self.cfg.bedrock_max_retries + 2):
            try:
                return self._call_bedrock(transcript, source, title)
            except botocore.exceptions.ClientError as e:
                last_err = e
                if attempt <= self.cfg.bedrock_max_retries:
                    continue
                raise
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt <= self.cfg.bedrock_max_retries:
                    continue
                raise
        raise last_err or RuntimeError("Bedrock call failed without exception?")

    def _call_bedrock(self, transcript: str, source: str, title: str) -> str:
        """Bedrock Claudeにプロンプトを渡してMarkdownを生成する。"""
        system_prompt = (
            "あなたは動画/音声/資料から得た文字起こしをMarkdownに整形するアシスタントです。\n"
            "出力規約:\n"
            "- # (H1): 章、## (H2): セクション、### (H3): 補足\n"
            "- 箇条書きは '-' を使用\n"
            "- 1段落=1トピック\n"
            "- 各段落末尾にタイムコード (HH:MM:SS–HH:MM:SS) を付与。情報が無ければ省略してよい\n"
            "- 可能なら source=... で元ファイル名を括弧内に追記\n"
            "- YAMLフロントマター（---で始まるメタ情報ヘッダ）は出力しない\n"
            f"- 出自: {source}\n"
        )
        user_prompt = (
            f"タイトル: {title}\n"
            "以下のテキストをMarkdown規約に沿って整形してください。\n\n"
            f"{transcript}"
        )
        import json

        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
            ],
            "system": [{"type": "text", "text": system_prompt}],
            "max_tokens": 4000,
            "temperature": 0.2,
        }
        body = json.dumps(payload).encode("utf-8")
        response = self.client.invoke_model(
            modelId=self.cfg.bedrock_model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = response.get("body")
        if hasattr(result, "read"):
            result = result.read()
        data = json.loads(result)
        return data["content"][0]["text"]

    def _prepend_metadata(
        self,
        markdown: str,
        category: Optional[str],
        source: str,
        source_uri: Optional[str],
        lecture_id: str | None,
    ) -> str:
        """Markdown先頭にメタ情報（YAMLフロントマター）を付与する。"""
        if self.has_front_matter(markdown):
            return markdown

        source_type = source

        source_path = ""
        if source_uri:
            if source_uri.startswith("s3://"):
                _, key = parse_s3_uri(source_uri)
                source_path = key
            else:
                source_path = source_uri

        header = self._yaml_front_matter(
            course_id=self.cfg.course_id,
            category=category if (category and category.strip()) else self.cfg.default_logical_category,
            source_path=source_path,
            source_type=source_type,
            lecture_id=lecture_id or "",
        )
        return header + "\n" + markdown.lstrip()

    def has_front_matter(self, markdown: str) -> bool:
        """YAMLフロントマターが既に先頭にあるか判定する。"""
        s = markdown.lstrip()
        if not s.startswith("---\n"):
            return False
        # 2つ目の --- までをフロントマター扱い
        end = s.find("\n---", 4)
        if end == -1:
            return False
        return True

    def has_lecture_id(self, markdown: str) -> bool:
        """フロントマター内に lecture_id があるか判定する。"""
        s = markdown.lstrip()
        if not s.startswith("---\n"):
            return False
        end = s.find("\n---", 4)
        if end == -1:
            return False
        header = s[: end + 4]
        return "lecture_id:" in header

    def backfill_front_matter(
        self, markdown_uri: str, category: str | None, source: str, source_uri: str | None, lecture_id: str | None
    ) -> bool:
        """既存Markdownにフロントマターが無ければ追記して上書きする。

        Returns:
            追記して更新した場合はTrue、既にあって更新不要ならFalse。
        """
        # 先頭だけ見て判定
        prefix = self.s3.read_prefix_text(markdown_uri, max_bytes=2048)
        has_header = self.has_front_matter(prefix)

        with self.s3.temp_local_copy(markdown_uri) as local_path:
            with open(local_path, "r", encoding="utf-8") as f:
                body = f.read()
        if has_header and lecture_id and not self.has_lecture_id(body):
            updated = self._insert_lecture_id(body, lecture_id)
        elif has_header:
            return False
        else:
            updated = self._prepend_metadata(
                body,
                category=category,
                source=source,
                source_uri=source_uri,
                lecture_id=lecture_id,
            )
        with tempfile.NamedTemporaryFile(delete=False, suffix=".md") as tmp:
            tmp_path = tmp.name
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(updated.strip() + "\n")
            self.s3.upload_file(tmp_path, markdown_uri)
        finally:
            try:
                os.remove(tmp_path)
            except FileNotFoundError:
                pass
        return True

    def _insert_lecture_id(self, markdown: str, lecture_id: str) -> str:
        """既存のフロントマターへ lecture_id を追記する。"""
        s = markdown.lstrip()
        if not s.startswith("---\n"):
            return markdown
        end = s.find("\n---", 4)
        if end == -1:
            return markdown
        header = s[4:end]
        if "lecture_id:" in header:
            return markdown
        if "course_id:" in header:
            import re

            def _inject(match):
                return match.group(0) + f"\nlecture_id: \"{lecture_id}\""

            header = re.sub(r"^course_id:.*$", _inject, header, count=1, flags=re.MULTILINE)
        else:
            header = header.rstrip("\n") + f"\nlecture_id: \"{lecture_id}\"\n"
        return f"---\n{header}\n---\n" + s[end + 4 :].lstrip("\n")

    def _yaml_front_matter(
        self, course_id: str, category: str, source_path: str, source_type: str, lecture_id: str
    ) -> str:
        """YAMLフロントマターを生成する。値は必ずダブルクォートで囲む。"""

        def q(v: str) -> str:
            v = v.replace("\\", "\\\\").replace('"', '\\"')
            return f"\"{v}\""

        lines = [
            "---",
            "# 変数の説明（未確定=TBD_*）",
            "# course_id: コース識別子",
            "# lecture_id: 講義ID",
            "# category: 論理カテゴリ（ジャンル/分類の代替）",
            "# source_path: raw/upload配下の相対パス",
            "# source_type: mv / pdf / html / csv など",
            "# TBD_genre_id: ジャンルID（未確定）",
            "# TBD_subgenre_id: サブジャンルID（未確定）",
            "# TBD_tags: タグ配列（未確定）",
            "# TBD_skills_to_learn: 学べるスキル配列（未確定）",
            "# TBD_course_name: コース名（未確定）",
            "# TBD_course_description: コース説明（未確定）",
            "# TBD_course_difficulty: コース難易度（未確定）",
            "# TBD_lecture_title: 講義名（未確定）",
            "# TBD_lecture_heading: 見出し（未確定）",
            "# TBD_lecture_description: 講義説明（未確定）",
            "# TBD_lecture_material_type: 教材種別（未確定）",
            "# TBD_scene_type: シーン種別（未確定）",
            "# TBD_pass_criteria: 合格条件（未確定）",
            "# TBD_proficiency_rubric: 評価基準（未確定）",
            "# TBD_followup_test_date: フォローアップ日（未確定）",
            "# TBD_scene_target_items: 出題範囲候補（未確定）",
            "# TBD_num_candidates: 生成候補数（未確定）",
            "# TBD_max_adopt: 採用上限（未確定）",
            "# TBD_num_questions_in_exam: 本番出題数（未確定）",
            f"course_id: {q(course_id)}",
            f"lecture_id: {q(lecture_id)}",
            f"category: {q(category)}",
            f"source_path: {q(source_path)}",
            f"source_type: {q(source_type)}",
            f"TBD_genre_id: {q('')}",
            f"TBD_subgenre_id: {q('')}",
            f"TBD_tags: {q('')}",
            f"TBD_skills_to_learn: {q('')}",
            f"TBD_course_name: {q('')}",
            f"TBD_course_description: {q('')}",
            f"TBD_course_difficulty: {q('')}",
            f"TBD_lecture_title: {q('')}",
            f"TBD_lecture_heading: {q('')}",
            f"TBD_lecture_description: {q('')}",
            f"TBD_lecture_material_type: {q('')}",
            f"TBD_scene_type: {q('')}",
            f"TBD_pass_criteria: {q('')}",
            f"TBD_proficiency_rubric: {q('')}",
            f"TBD_followup_test_date: {q('')}",
            f"TBD_scene_target_items: {q('')}",
            f"TBD_num_candidates: {q('')}",
            f"TBD_max_adopt: {q('')}",
            f"TBD_num_questions_in_exam: {q('')}",
            "---",
        ]
        return "\n".join(lines)
