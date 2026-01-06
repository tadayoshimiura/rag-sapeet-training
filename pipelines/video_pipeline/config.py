"""動画パイプラインの設定定義。"""
from pydantic import BaseModel, Field


class PipelineConfig(BaseModel):
    """パイプラインの設定（できるだけハードコードしない）。"""

    bucket: str = Field(default="bucket", description="対象S3バケット名。")
    course_id: str = Field(default="course_id=test_00", description="講座ID（course_id=... 形式）。")
    ffmpeg_path: str = Field(default="ffmpeg", description="ffmpegのパス。")
    sample_rate_hz: int = Field(default=16000, description="ASR入力用のサンプルレート（Hz）。")
    chunk_minutes_min: int = Field(default=5, description="音声分割の最小長（分）。")
    chunk_minutes_max: int = Field(default=15, description="音声分割の最大長（分）。")
    asr_mode: str = Field(default="whisper", description="whisper または faster-whisper を指定。")
    asr_model: str = Field(default="base", description="ASRモデル名（例: base / small / medium など）。")
    asr_max_retries: int = Field(default=2, description="ASR失敗時のリトライ回数。")
    asr_max_workers: int = Field(default=2, description="ASR並列実行の最大ワーカー数。")
    bedrock_model_id: str = Field(
        default="anthropic.claude-3-5-sonnet-20240620-v1:0",
        description="整形に使用するLLMのモデルID（現状はBedrockを想定）。",
    )
    bedrock_region: str | None = Field(
        default=None, description="LLMのリージョン。未指定なら環境変数AWS_REGIONを利用。"
    )
    bedrock_max_retries: int = Field(default=2, description="LLM呼び出し失敗時のリトライ回数。")
    bedrock_max_workers: int = Field(default=2, description="Markdown整形の並列ワーカー数（ローカル並列）。")
    bedrock_chunk_chars: int = Field(
        default=12000,
        description="Bedrock入力が長すぎる場合に分割する文字数（超過でチャンク化）。",
    )
    default_logical_category: str = Field(
        default="unclassified",
        description="分類が不明な場合にMarkdownヘッダへ入れる論理カテゴリ。",
    )
    csv_mapping_path: str = Field(
        default="configs/csv_settings.yml",
        description="CSV列のマッピング定義ファイル（列名→意味）。",
    )
    csv_genre_rules_path: str = Field(
        default="configs/csv_settings.yml",
        description="CSVのジャンル自動判定ルール（キーワードベース）。",
    )

    class Config:
        frozen = True
