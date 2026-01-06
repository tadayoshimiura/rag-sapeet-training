"""動画から音声を抽出する。"""
import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List

from .config import PipelineConfig
from .s3_utils import S3Client


def _run_ffmpeg(args: list) -> None:
    proc = subprocess.run(args, check=True, capture_output=True)
    if proc.stderr:
        # keep stderr handy for debugging if needed
        pass


def extract_audio(movie_uri: str, dest_uri: str, cfg: PipelineConfig) -> None:
    """動画からモノラル16kHzのWAVを抽出してアップロードする。

    Args:
        movie_uri: 入力動画のパス（s3:// またはローカルパス）。
        dest_uri: 抽出後の音声を配置するS3 URI。
        cfg: ffmpegパスやサンプリング設定を含むパイプライン設定。
    """
    s3 = S3Client(bucket=cfg.bucket)
    with tempfile.TemporaryDirectory() as tmpdir:
        movie_path = Path(tmpdir) / Path(movie_uri).name
        wav_path = Path(tmpdir) / (movie_path.stem + ".wav")
        if movie_uri.startswith("s3://"):
            s3.download_file(movie_uri, str(movie_path))
        else:
            # local path
            os.link(movie_uri, movie_path)
        _run_ffmpeg(
            [
                cfg.ffmpeg_path,
                "-i",
                str(movie_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(cfg.sample_rate_hz),
                str(wav_path),
            ]
        )
        s3.upload_file(str(wav_path), dest_uri)


def split_audio(audio_uri: str, dest_prefix: str, cfg: PipelineConfig, target_minutes: int = 10) -> List[str]:
    """音声をチャンク（5〜15分目安）に分割してアップロードする。

    Args:
        audio_uri: 分割対象の音声（s3:// またはローカルパス）。
        dest_prefix: 分割後ファイルを配置するS3プレフィックス。
        cfg: 分割時間やffmpegパスを含むパイプライン設定。
        target_minutes: 目標チャンク長（分）。最小・最大にクランプされる。

    Returns:
        分割後WAVのS3 URIリスト。
    """
    s3 = S3Client(bucket=cfg.bucket)
    chunk_uris: List[str] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / Path(audio_uri).name
        if audio_uri.startswith("s3://"):
            s3.download_file(audio_uri, str(src_path))
        else:
            os.link(audio_uri, src_path)

        # probe duration
        probe = subprocess.run(
            [
                cfg.ffmpeg_path,
                "-i",
                str(src_path),
                "-hide_banner",
            ],
            capture_output=True,
            text=True,
        )
        duration_seconds = None
        for line in probe.stderr.splitlines():
            if "Duration" in line:
                # Duration: 00:10:05.12
                ts = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = ts.split(":")
                duration_seconds = int(float(h) * 3600 + float(m) * 60 + float(s))
                break
        if duration_seconds is None:
            raise RuntimeError("Could not parse duration from ffmpeg output")

        ideal = min(cfg.chunk_minutes_max, max(cfg.chunk_minutes_min, target_minutes))
        chunk_len = ideal * 60
        parts = max(1, math.ceil(duration_seconds / chunk_len))

        for idx in range(parts):
            start = idx * chunk_len
            out_path = Path(tmpdir) / f"{src_path.stem}_part{idx:02d}.wav"
            _run_ffmpeg(
                [
                    cfg.ffmpeg_path,
                    "-ss",
                    str(start),
                    "-i",
                    str(src_path),
                    "-t",
                    str(chunk_len),
                    "-c",
                    "copy",
                    str(out_path),
                ]
            )
            dest_uri = f"{dest_prefix}{out_path.name}"
            s3.upload_file(str(out_path), dest_uri)
            chunk_uris.append(dest_uri)
    return chunk_uris
