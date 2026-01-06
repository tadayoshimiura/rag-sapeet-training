"""フォルダ構成の整形ルール。"""
from dataclasses import dataclass

from .config import PipelineConfig


@dataclass(frozen=True)
class Layout:
    """S3 layout helper for a given course."""

    cfg: PipelineConfig

    @property
    def raw_upload(self) -> str:
        return f"s3://{self.cfg.bucket}/raw/course_packages/{self.cfg.course_id}/upload/"

    @property
    def processed_root(self) -> str:
        return f"s3://{self.cfg.bucket}/processed/{self.cfg.course_id}/"

    @property
    def extracted_pdf(self) -> str:
        return self.processed_root + "extracted/pdf/"

    @property
    def extracted_video(self) -> str:
        return self.processed_root + "extracted/video/"

    @property
    def extracted_audio(self) -> str:
        return self.processed_root + "extracted/audio/"

    @property
    def extracted_html(self) -> str:
        return self.processed_root + "extracted/html/"

    @property
    def audio(self) -> str:
        return self.processed_root + "audio/"

    @property
    def audio_extracted(self) -> str:
        return self.processed_root + "audio/extracted/"

    @property
    def audio_chunks(self) -> str:
        return self.processed_root + "audio/chunks/"

    @property
    def transcript_raw(self) -> str:
        return self.processed_root + "transcript/raw/"

    @property
    def transcript_normalized(self) -> str:
        return self.processed_root + "transcript/normalized/"

    @property
    def ocr_raw(self) -> str:
        return self.processed_root + "ocr/raw/"

    @property
    def ocr_normalized(self) -> str:
        return self.processed_root + "ocr/normalized/"

    def ocr_raw_with_category(self, category: str) -> str:
        """OCR生出力のカテゴリ別配置。例: '仕事の基礎'。"""
        return self.ocr_raw + f"{category}/"

    def ocr_normalized_with_category(self, category: str) -> str:
        """OCR軽整形のカテゴリ別配置。"""
        return self.ocr_normalized + f"{category}/"

    @property
    def kb_markdown_v1(self) -> str:
        return f"s3://{self.cfg.bucket}/course_store/{self.cfg.course_id}/knowledge_md/v1/"

    def kb_markdown_v1_for_lecture(self, lecture_id: str) -> str:
        """講義ID単位のMarkdown保存先。例: '仕事の基礎' / '言語/Python初級'。"""
        lecture_id = lecture_id.strip("/").strip()
        if not lecture_id:
            return self.kb_markdown_v1
        return self.kb_markdown_v1 + lecture_id + "/"

    @property
    def kb_markdown_v2(self) -> str:
        return f"s3://{self.cfg.bucket}/course_store/{self.cfg.course_id}/knowledge_md/v2/"

    @property
    def kb_summary(self) -> str:
        """講義要約（summary）の保存先ルート。"""
        return f"s3://{self.cfg.bucket}/course_store/{self.cfg.course_id}/summary/"

    @classmethod
    def for_course(cls, course_id: str, bucket: str = "bucket") -> "Layout":
        cfg = PipelineConfig(course_id=course_id, bucket=bucket)
        return cls(cfg=cfg)
