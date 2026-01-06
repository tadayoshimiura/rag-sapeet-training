"""CSV入力の処理。"""
from __future__ import annotations

import csv
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .config import PipelineConfig
from .layout import Layout
from .lecture_map import resolve_lecture_from_source
from .s3_utils import S3Client, parse_s3_uri


@dataclass
class CsvProcessor:
    """CSVをMarkdownに変換する（主に教材パーツの結合）。"""

    cfg: PipelineConfig

    def __post_init__(self) -> None:
        self.s3 = S3Client(bucket=self.cfg.bucket)
        self.layout = Layout(cfg=self.cfg)

    def process_csv_to_markdown(self, csv_uri: str, dest_subpath: str) -> str:
        """CSVを解析し、セクション/パート順にMarkdownへ結合してcourse_storeへ出力する。

        Args:
            csv_uri: 入力CSVのS3 URI。
            dest_subpath: raw/upload 配下の相対パス（lecture_id 推定に利用）。

        Returns:
            出力MarkdownのS3 URI。
        """
        rows = self._read_rows(csv_uri)
        course_id, lecture_id = resolve_lecture_from_source(self.cfg, csv_uri, fallback=dest_subpath or None)
        markdown = self._rows_to_markdown(
            rows,
            source_uri=csv_uri,
            dest_subpath=dest_subpath,
            course_id=course_id,
            lecture_id=lecture_id,
        )

        dest_root = self.layout.kb_markdown_v1_for_lecture(lecture_id)
        dest = dest_root + Path(csv_uri).stem + ".md"
        self._upload_text(markdown, dest)
        return dest

    def _read_rows(self, csv_uri: str) -> List[Dict[str, str]]:
        with self.s3.temp_local_copy(csv_uri) as local_path:
            raw = Path(local_path).read_bytes()
            enc = self._detect_encoding(raw)
            text = raw.decode(enc, errors="strict")
            # 改行がCSV内部にも入るため、newline=''でDictReaderに渡す
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                tmp_path = tmp.name
            try:
                Path(tmp_path).write_text(text, encoding="utf-8", newline="")
                with open(tmp_path, "r", encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f)
                    rows = [r for r in reader]
            finally:
                try:
                    os.remove(tmp_path)
                except FileNotFoundError:
                    pass
        return rows

    def _detect_encoding(self, raw: bytes) -> str:
        """最低限の判定（今回のCSVはcp932想定だが、utf-8も受ける）。"""
        for enc in ("utf-8-sig", "utf-8", "cp932"):
            try:
                raw.decode(enc)
                return enc
            except Exception:
                continue
        return "utf-8"

    def _rows_to_markdown(
        self,
        rows: List[Dict[str, str]],
        source_uri: str,
        dest_subpath: str,
        course_id: str,
        lecture_id: str,
    ) -> str:
        if not rows:
            raise ValueError("CSVに行がありません")

        mapping = self._load_mapping()
        category = self._infer_category_from_rows(rows, dest_subpath=dest_subpath, mapping=mapping)
        course_id = self._infer_course_id_from_rows(rows, mapping=mapping) or course_id

        # 安定ソート（section_order→part_order）
        def to_int(v: Optional[str]) -> int:
            try:
                return int(v or 0)
            except Exception:
                return 0

        rows_sorted = sorted(
            rows,
            key=lambda r: (
                to_int(r.get(mapping.get("section_order", "section_order"))),
                to_int(r.get(mapping.get("part_order", "part_order"))),
            ),
        )

        header = self._yaml_front_matter(
            course_id=course_id,
            lecture_id=lecture_id,
            category=category,
            source_path=self._source_path(source_uri),
            source_type="csv",
        )

        parts: List[str] = [header]
        current_section_id: Optional[str] = None
        for r in rows_sorted:
            section_id = r.get(mapping.get("section_id", "section_id")) or ""
            section_title = (r.get(mapping.get("section_title", "section_title")) or "").strip()
            part_title = (r.get(mapping.get("part_title", "part_title")) or "").strip()
            part_text = (r.get(mapping.get("part_text", "part_text")) or "").strip()
            if section_id != current_section_id:
                current_section_id = section_id
                if section_title:
                    parts.append(f"# {section_title}\n")
            if part_title:
                parts.append(f"## {part_title}\n")
            if part_text:
                parts.append(part_text.strip() + "\n")

        return "\n".join(p.strip("\n") for p in parts if p is not None).strip() + "\n"

    def _load_mapping(self) -> Dict[str, str]:
        """CSV列名のマッピング定義を読む（未定義ならデフォルトへ退避）。"""
        default = {
            "course_id": "course_id",
            "section_id": "section_id",
            "section_title": "section_title",
            "section_order": "section_order",
            "part_title": "part_title",
            "part_text": "part_text",
            "part_order": "part_order",
        }
        path = Path(self.cfg.csv_mapping_path)
        if not path.exists():
            return default
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        mapping = data.get("columns", {}) if isinstance(data, dict) else {}
        if not isinstance(mapping, dict):
            return default
        merged = {**default, **mapping}
        return merged

    def _source_path(self, source_uri: str) -> str:
        if not source_uri.startswith("s3://"):
            return source_uri
        _, key = parse_s3_uri(source_uri)
        return key

    def _yaml_front_matter(
        self, course_id: str, lecture_id: str, category: str, source_path: str, source_type: str
    ) -> str:
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

    def _upload_text(self, text: str, dest_uri: str) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".md") as tmp:
            tmp_path = tmp.name
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(text)
            self.s3.upload_file(tmp_path, dest_uri)
        finally:
            try:
                os.remove(tmp_path)
            except FileNotFoundError:
                pass

    def _infer_category_from_rows(
        self, rows: List[Dict[str, str]], dest_subpath: str, mapping: Dict[str, str]
    ) -> str:
        """CSV本文からジャンル（論理カテゴリ）を推定する。"""
        rules = self._load_genre_rules()
        if rules:
            text_blob = self._collect_text_for_genre(rows, mapping=mapping)
            best = self._pick_genre_by_keywords(text_blob, rules)
            if best:
                return best
        from_path = self._infer_category_from_subpath(dest_subpath)
        if from_path:
            return from_path
        return self.cfg.default_logical_category

    def _infer_course_id_from_rows(self, rows: List[Dict[str, str]], mapping: Dict[str, str]) -> Optional[str]:
        """CSVに course_id 列がある場合は、1行目の値を採用する（CSV=1コース前提）。"""
        key = mapping.get("course_id", "course_id")
        if not rows:
            return None
        value = (rows[0].get(key) or "").strip()
        return value or None

    def _collect_text_for_genre(self, rows: List[Dict[str, str]], mapping: Dict[str, str]) -> str:
        """ジャンル推定用のテキストを集約する（過大化しないよう軽量に）。"""
        fields = [
            mapping.get("section_title", "section_title"),
            mapping.get("part_title", "part_title"),
            mapping.get("part_text", "part_text"),
        ]
        buf: List[str] = []
        for r in rows[:300]:
            for f in fields:
                v = (r.get(f) or "").strip()
                if v:
                    buf.append(v)
        return "\n".join(buf)

    def _pick_genre_by_keywords(self, text: str, rules: List[Dict[str, object]]) -> Optional[str]:
        """キーワード一致数が最大のカテゴリを返す。"""
        if not text:
            return None
        text_lower = text.lower()
        best_cat = None
        best_score = 0
        for rule in rules:
            category = str(rule.get("category", "")).strip()
            keywords = rule.get("keywords", [])
            if not category or not isinstance(keywords, list):
                continue
            score = 0
            for kw in keywords:
                if not isinstance(kw, str) or not kw:
                    continue
                score += text_lower.count(kw.lower())
            if score > best_score:
                best_score = score
                best_cat = category
        return best_cat if best_score > 0 else None

    def _infer_category_from_subpath(self, dest_subpath: str) -> Optional[str]:
        """upload配下のパスからカテゴリ候補を拾う。"""
        parts = [p for p in (dest_subpath or "").split("/") if p]
        for p in parts:
            if p in {"未分類", "unclassified"}:
                continue
            return p
        return None

    def _load_genre_rules(self) -> List[Dict[str, object]]:
        """CSVのジャンル推定ルールを読み込む。"""
        path = Path(self.cfg.csv_genre_rules_path)
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return []
        rules = data.get("rules", [])
        return rules if isinstance(rules, list) else []
