"""動画→テキストの全体パイプライン。"""
import json
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from .asr import ASRRunner, AsrStat
from .audio import extract_audio, split_audio
from .config import PipelineConfig
from .csv_processor import CsvProcessor
from .layout import Layout
from .lecture_map import resolve_lecture_from_source
from .markdown_formatter import MarkdownFormatter
from .pdf_processor import PdfProcessor
from .s3_utils import S3Client, parse_s3_uri

log = logging.getLogger(__name__)


class VideoPipeline:
    """docs/rag_video_pipeline.md に従うパイプライン骨子。既存RAG資産には非接触。
    TODOは実行基盤（EKS/キュー）に合わせて埋める。"""

    def __init__(self, cfg: PipelineConfig, ocr_backend=None):
        self.cfg = cfg
        self.layout = Layout(cfg=cfg)
        self.asr_runner = ASRRunner(cfg)
        self.formatter = MarkdownFormatter(cfg)
        self.s3 = S3Client(bucket=cfg.bucket)
        self.pdf = PdfProcessor(cfg, ocr_backend=ocr_backend)
        self.csv = CsvProcessor(cfg)

    def load_status_document(self) -> dict:
        """processed/_status.json の全体ドキュメントを読み込む。存在しなければ空dict。"""
        status_uri = f"{self.layout.processed_root}_status.json"
        try:
            with self.s3.temp_local_copy(status_uri) as path:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except FileNotFoundError:
            return {}

    def update_file_status(self, input_uri: str, etag: str, markdown_uri: str, errors: list[str]) -> None:
        """入力ファイル単位の状態（ETag/出力/エラー）を _status.json に追記する。"""
        doc = self.load_status_document()
        files = doc.get("files") or {}
        files[input_uri] = {
            "etag": etag,
            "markdown": markdown_uri,
            "errors": errors,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        doc["files"] = files
        self._write_status_document(doc)

    def ensure_markdown_metadata(
        self, markdown_uri: str, source: str, category: str | None, source_uri: str | None, lecture_id: str | None
    ) -> bool:
        """既存Markdownにメタ情報が無ければ追記する。"""
        return self.formatter.backfill_front_matter(
            markdown_uri,
            category=category,
            source=source,
            source_uri=source_uri,
            lecture_id=lecture_id,
        )

    # ---- Stage 1: ingestion / extraction ---------------------------------
    def stage_extract_audio(self, movie_uri: str) -> str:
        """動画から音声を抽出して processed/audio/extracted に配置する。

        Args:
            movie_uri: 入力動画のS3 URI。

        Returns:
            抽出後WAVのS3 URI。
        """
        dest = self.layout.audio_extracted + Path(movie_uri).stem + ".wav"
        log.info("extract audio: %s -> %s", movie_uri, dest)
        extract_audio(movie_uri, dest, self.cfg)
        return dest

    def stage_split_audio(self, audio_uri: str) -> List[str]:
        """抽出音声を5–15分チャンクに分割し processed/audio/chunks に配置する。

        Args:
            audio_uri: 分割対象のWAV S3 URI。

        Returns:
            分割後チャンクのS3 URIリスト。
        """
        log.info("split audio: %s", audio_uri)
        return split_audio(audio_uri, dest_prefix=self.layout.audio_chunks, cfg=self.cfg)

    # ---- Stage 2: ASR -----------------------------------------------------
    def stage_asr(self, chunk_uris: Iterable[str]) -> tuple[List[str], list[str], list[AsrStat]]:
        """チャンクにASRをかけ、transcript/raw に配置する。

        Args:
            chunk_uris: 処理対象チャンクのS3 URI群。

        Returns:
            (transcript/raw 配下の出力S3 URIリスト, エラーリスト, ASR統計) のタプル。
        """
        return self.asr_runner.run(chunk_uris)

    def stage_merge_and_fix(self, transcript_parts: Iterable[str]) -> tuple[str, list[str]]:
        """生起こしを結合し、簡易整形して transcript/normalized に配置。

        Args:
            transcript_parts: transcript/raw のテキストURI群。

        Returns:
            (transcript/normalized 配下に書き出すS3 URI, エラーリスト) のタプル。
        """
        dest = self.layout.transcript_normalized + "merged.txt"
        log.info("merge transcripts -> %s", dest)
        texts: List[str] = []
        errors: List[str] = []
        for uri in transcript_parts:
            with self.s3.temp_local_copy(uri) as path:
                with open(path, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                    if not raw:
                        errors.append(f"empty transcript: {uri}")
                        continue
                    texts.append(self._normalize_text(raw))

        merged = "\n\n".join([t for t in texts if t])
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
            tmp_path = tmp.name
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(merged + "\n")
            self.s3.upload_file(tmp_path, dest)
        finally:
            try:
                os.remove(tmp_path)
            except FileNotFoundError:
                pass
        return dest, errors

    def _normalize_text(self, text: str) -> str:
        """簡易正規化（ノイズ除去・空行圧縮・句読点補正・前後空白除去）。"""
        import re

        cleaned = text
        # よくあるノイズタグを削除
        cleaned = re.sub(r"\[(music|applause|silence|noise)\]", "", cleaned, flags=re.IGNORECASE)
        # 連続空白を1つに
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        # 3行以上の連続改行を2行に圧縮
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        # 行頭行末の空白除去
        cleaned = "\n".join(line.strip() for line in cleaned.splitlines())
        # 先頭末尾の空行を除去
        cleaned = cleaned.strip()

        # 句読点補正（行末に句点を追加・連続句読点を1つに）
        def _fix_sentence_end(line: str) -> str:
            # 既に句読点や記号で終わっていればそのまま
            if re.search(r"[。．.!?！？]$", line):
                return line
            # 括弧・引用で終わっている場合もそのまま
            if re.search(r"[））」』]$", line):
                return line
            # 英数字のみで終わる場合はピリオド、その他は全角句点
            if re.search(r"[A-Za-z0-9]$", line):
                return line + "."
            return line + "。"

        normalized_lines = []
        for line in cleaned.splitlines():
            # 連続句読点を1つに
            line = re.sub(r"[。．]{2,}", "。", line)
            line = re.sub(r"[!！]{2,}", "！", line)
            line = re.sub(r"[?？]{2,}", "？", line)
            line = _fix_sentence_end(line)
            normalized_lines.append(line)

        cleaned = "\n".join(normalized_lines)

        return cleaned

    # ---- Stage 3: Markdown formatting -------------------------------------
    def stage_format_markdown(
        self,
        normalized_uri: str,
        source: str,
        lecture_id: str,
        title: str | None = None,
        meta_category: str | None = None,
        source_uri: str | None = None,
    ) -> str:
        """正規化済みテキストをMarkdown契約に沿って整形し、course_storeへ出力。

        Args:
            normalized_uri: transcript/normalized の入力テキストURI。
            source: 出自を示すキー（mv/pdf/audio/html/csv）。
            lecture_id: 講義ID（出力先のフォルダ名）。
            title: 出力ファイル名のベースに使う文字列。未指定なら normalized のstem。
            meta_category: Markdownヘッダに入れる論理カテゴリ。未指定なら default_logical_category。
            source_uri: 元データのS3 URI（メタ情報ヘッダに埋め込む）。

        Returns:
            course_store/<course_id>/knowledge_md/v1/<lecture_id>/ 配下のS3 URI。
        """
        dest = self.formatter.format(
            normalized_uri,
            source=source,
            lecture_id=lecture_id,
            dest_name=title,
            meta_category=meta_category,
            source_uri=source_uri,
        )
        log.info("format markdown: %s -> %s", normalized_uri, dest)
        return dest

    # ---- PDF用ステージ ----------------------------------------------------
    def stage_process_pdf(self, pdf_uri: str, category: str) -> tuple[str, str]:
        """PDFをテキスト化し、ocr/raw・ocr/normalized へ配置。"""
        return self.pdf.process_pdf(pdf_uri, category)

    # ---- Orchestration ----------------------------------------------------
    def run_for_movie(self, movie_uri: str, resume_failed: bool = False) -> str:
        """1本の動画を end-to-end で処理するスタブ。

        Args:
            movie_uri: 入力動画のS3 URI。
            resume_failed: 前回失敗したチャンクのみ再ASRするか。

        Returns:
            course_store/<course_id>/knowledge_md/v1/<lecture_id> 配下のMarkdown URI。
        """
        t0 = time.time()
        audio = self.stage_extract_audio(movie_uri)
        t_extract = time.time()
        chunks = self.stage_split_audio(audio)
        t_split = time.time()
        reuse_transcripts: List[str] = []
        reuse_chunks: List[str] = []
        if resume_failed:
            last = self._load_last_run()
            if last and last.get("movie") == movie_uri and last.get("asr_stats"):
                reuse_transcripts, pending_chunks = self._reuse_successful_asr(last["asr_stats"], chunks)
                reuse_chunks = [stat["chunk"] for stat in last["asr_stats"] if stat.get("transcript")]
                chunks = pending_chunks
                log.info("resume: reuse %d transcripts, rerun %d chunks", len(reuse_transcripts), len(chunks))
        transcripts, asr_errors, asr_stats = self.stage_asr(chunks)
        t_asr = time.time()
        all_transcripts = reuse_transcripts + transcripts
        normalized, merge_errors = self.stage_merge_and_fix(all_transcripts)
        t_merge = time.time()
        md = None
        format_errors: list[str] = []
        last = self._load_last_run()
        if resume_failed and last and last.get("movie") == movie_uri and last.get("markdown") and not last.get("errors"):
            md = last.get("markdown")
            log.info("resume: reuse existing markdown %s", md)
        else:
            try:
                course_id, lecture_id = resolve_lecture_from_source(
                    self.cfg, movie_uri, fallback=self._infer_category(movie_uri)
                )
                if course_id != self.cfg.course_id:
                    log.info("override course_id: %s -> %s", self.cfg.course_id, course_id)
                md = self.stage_format_markdown(
                    normalized,
                    source="mv",
                    lecture_id=lecture_id,
                    title=Path(movie_uri).stem,
                    meta_category=lecture_id,
                    source_uri=movie_uri,
                )
            except Exception as e:  # noqa: BLE001
                format_errors.append(f"format failed: {e}")
                md = ""
        t_format = time.time()
        self._write_status(
            movie_uri=movie_uri,
            audio_uri=audio,
            chunk_uris=reuse_chunks + chunks,
            transcript_uris=all_transcripts,
            normalized_uri=normalized,
            markdown_uri=md,
            errors=asr_errors + merge_errors + format_errors,
            asr_stats=asr_stats,
            timings={
                "extract_ms": int((t_extract - t0) * 1000),
                "split_ms": int((t_split - t_extract) * 1000),
                "asr_ms": int((t_asr - t_split) * 1000),
                "merge_ms": int((t_merge - t_asr) * 1000),
                "format_ms": int((t_format - t_merge) * 1000),
                "total_ms": int((t_format - t0) * 1000),
            },
        )
        return md

    def _write_status(
        self,
        movie_uri: str,
        audio_uri: str,
        chunk_uris: list[str],
        transcript_uris: list[str],
        normalized_uri: str,
        markdown_uri: str,
        errors: list[str],
        asr_stats: list[AsrStat],
        timings: dict,
    ) -> None:
        """進捗・成果・エラーを _status.json に記録する。"""
        doc = self.load_status_document()
        payload = {
            "last_run": {
                "movie": movie_uri,
                "audio": audio_uri,
                "chunks": chunk_uris,
                "transcripts_raw": transcript_uris,
                "transcript_normalized": normalized_uri,
                "markdown": markdown_uri,
                "errors": errors,
                "asr_stats": asr_stats,
                "timings": timings,
                "asr_mode": self.cfg.asr_mode,
                "asr_model": self.cfg.asr_model,
                "bedrock_model_id": self.cfg.bedrock_model_id,
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }
        }
        doc.update(payload)

        # ファイル単位でも更新（動画）
        try:
            etag = self.s3.head(movie_uri).get("etag", "")
        except Exception:  # noqa: BLE001
            etag = ""
        files = doc.get("files") or {}
        files[movie_uri] = {
            "etag": etag,
            "markdown": markdown_uri,
            "errors": errors,
            "asr_mode": self.cfg.asr_mode,
            "asr_model": self.cfg.asr_model,
            "bedrock_model_id": self.cfg.bedrock_model_id,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        doc["files"] = files
        self._write_status_document(doc)

    def _write_status_document(self, doc: dict) -> None:
        """processed/_status.json に書き戻す。"""
        status_uri = f"{self.layout.processed_root}_status.json"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
            tmp_path = tmp.name
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)
            self.s3.upload_file(tmp_path, status_uri)
        finally:
            try:
                os.remove(tmp_path)
            except FileNotFoundError:
                pass

    def _load_last_run(self) -> Optional[dict]:
        """前回の _status.json を読み込む。"""
        status_uri = f"{self.layout.processed_root}_status.json"
        try:
            with self.s3.temp_local_copy(status_uri) as path:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("last_run")
        except FileNotFoundError:
            return None

    def _reuse_successful_asr(self, stats: list[AsrStat], current_chunks: List[str]) -> tuple[List[str], List[str]]:
        """前回成功済みのASR結果を再利用し、未処理チャンクだけ返す。"""
        success = {s["chunk"]: s["transcript"] for s in stats if s.get("transcript") and not s.get("error")}
        reuse_transcripts = []
        pending_chunks = []
        for chunk in current_chunks:
            if chunk in success:
                reuse_transcripts.append(success[chunk])
            else:
                pending_chunks.append(chunk)
        return reuse_transcripts, pending_chunks

    def _infer_category(self, movie_uri: str) -> str:
        """動画URIから講座カテゴリ名を推定する。"""
        p = Path(movie_uri)
        parts = p.parts
        if "upload" in parts:
            idx = parts.index("upload")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        if "extracted" in parts:
            idx = parts.index("extracted")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return p.parent.name

    def _infer_subpath_under_upload(self, uri: str) -> str:
        """raw/upload配下の相対パス（ファイル名を除く）を返す。"""
        if not uri.startswith("s3://"):
            return ""
        _, key = parse_s3_uri(uri)
        parts = key.split("/")
        if "upload" not in parts:
            return ""
        idx = parts.index("upload")
        # upload/<...>/<filename>
        if idx + 1 >= len(parts) - 1:
            return ""
        sub = parts[idx + 1 : -1]
        return "/".join([p for p in sub if p])

    # ---- PDF専用オーケストレーション --------------------------------------
    def run_for_pdf(self, pdf_uri: str) -> str:
        """PDF1本をテキスト化してMarkdownまで出力する。

        Args:
            pdf_uri: 入力PDFのS3 URI。

        Returns:
            course_store/<course_id>/knowledge_md/v1/<lecture_id> 配下のMarkdown URI。
        """
        dest_category = self._infer_category(pdf_uri)
        raw_uri, norm_uri = self.stage_process_pdf(pdf_uri, dest_category)
        course_id, lecture_id = resolve_lecture_from_source(self.cfg, pdf_uri, fallback=dest_category)
        md = self.stage_format_markdown(
            norm_uri,
            source="pdf",
            lecture_id=lecture_id,
            title=Path(pdf_uri).stem,
            meta_category=lecture_id,
            source_uri=pdf_uri,
        )
        return md

    def run_for_csv(self, csv_uri: str) -> str:
        """CSV1本をMarkdownに結合して出力する。"""
        subpath = self._infer_subpath_under_upload(csv_uri)
        return self.csv.process_csv_to_markdown(csv_uri, dest_subpath=subpath)
