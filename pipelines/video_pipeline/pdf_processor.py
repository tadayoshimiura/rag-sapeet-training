"""PDFのOCR/テキスト抽出。"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pypdf import PdfReader

from .config import PipelineConfig
from .layout import Layout
from .s3_utils import S3Client


class OCRBackend(Protocol):
    """OCRバックエンドのインターフェース。交換可能にするための最低限の契約。"""

    def run(self, pdf_path: str) -> str:
        """PDFをOCRしてUTF-8テキストを返す。"""
        ...


@dataclass
class PdfProcessor:
    """PDFのテキスト層判定と抽出/OCRをまとめる。"""

    cfg: PipelineConfig
    ocr_backend: OCRBackend | None = None

    def __post_init__(self) -> None:
        self.s3 = S3Client(bucket=self.cfg.bucket)
        self.layout = Layout(cfg=self.cfg)

    def has_text_layer(self, pdf_path: str, min_chars: int = 32, max_pages: int = 5) -> bool:
        """テキスト層の有無を判定する。先頭数ページで十分量の文字があれば True。"""
        try:
            reader = PdfReader(pdf_path)
            seen = 0
            for i, page in enumerate(reader.pages):
                if i >= max_pages:
                    break
                text = page.extract_text() or ""
                seen += len(text.strip())
                if seen >= min_chars:
                    return True
            return False
        except Exception:
            return False

    def extract_text_layer(self, pdf_path: str) -> str:
        """テキスト層を抽出する。失敗時は空文字を返す。"""
        try:
            reader = PdfReader(pdf_path)
            texts = []
            for page in reader.pages:
                txt = page.extract_text() or ""
                txt = txt.strip()
                if txt:
                    texts.append(txt)
            return "\n\n".join(texts).strip()
        except Exception:
            return ""

    def process_pdf(self, pdf_uri: str, category: str) -> tuple[str, str]:
        """PDFを処理して raw/normalized を返す。OCRはバックエンドを差し替え可能。

        Args:
            pdf_uri: 入力PDFのS3 URI。
            category: 講座カテゴリ（raw/uploadのサブフォルダ名）。

        Returns:
            (ocr/raw のS3 URI, ocr/normalized のS3 URI)
        """
        stem = Path(pdf_uri).stem
        dest_raw_root = self.layout.ocr_raw_with_category(category)
        dest_norm_root = self.layout.ocr_normalized_with_category(category)

        with self.s3.temp_local_copy(pdf_uri) as local_path:
            if self.has_text_layer(local_path):
                raw_text = self.extract_text_layer(local_path)
            else:
                if not self.ocr_backend:
                    raise RuntimeError("テキスト層なし。OCRバックエンドが設定されていません。")
                raw_text = self.ocr_backend.run(local_path)

        if not raw_text.strip():
            raise ValueError(f"PDFからテキストを取得できませんでした: {pdf_uri}")

        raw_uri = self._upload_text(raw_text, dest_raw_root, stem + ".txt")
        normalized_text = self._normalize_pdf_text(raw_text)
        norm_uri = self._upload_text(normalized_text, dest_norm_root, stem + ".txt")
        return raw_uri, norm_uri

    def _upload_text(self, text: str, dest_root: str, filename: str) -> str:
        dest = dest_root + filename
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
            tmp_path = tmp.name
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(text.strip() + "\n")
            self.s3.upload_file(tmp_path, dest)
        finally:
            try:
                os.remove(tmp_path)
            except FileNotFoundError:
                pass
        return dest

    def _normalize_pdf_text(self, text: str) -> str:
        """PDF抽出テキストの軽整形。空白圧縮と行頭末トリムのみ。"""
        import re

        cleaned = text.replace("\r\n", "\n")
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = "\n".join(line.strip() for line in cleaned.splitlines())
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()
