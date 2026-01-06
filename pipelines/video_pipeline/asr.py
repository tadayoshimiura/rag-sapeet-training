"""ASR（Whisper/faster-whisper）の実行。"""
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, List, Optional, TypedDict

from .config import PipelineConfig
from .s3_utils import S3Client


class AsrStat(TypedDict, total=False):
    """ASRチャンク処理の統計。"""

    chunk: str
    transcript: str | None
    elapsed_ms: int
    error: str | None
    avg_confidence: float | None


class ASRRunner:
    """ASR実行の枠。Whisper系（whisper か faster-whisper）を選択可能。"""

    def __init__(self, cfg: PipelineConfig, model_path: Optional[str] = None):
        self.cfg = cfg
        self.model_path = model_path
        self.s3 = S3Client(bucket=cfg.bucket)

    def run(self, chunk_uris: Iterable[str]) -> tuple[List[str], List[str], List[AsrStat]]:
        """音声チャンクをASRにかけ、raw transcriptをS3に配置する。

        Args:
            chunk_uris: 処理対象の音声チャンクS3 URI群。

        Returns:
            (transcript/raw 配下のURIリスト, エラーリスト, チャンク統計リスト) のタプル。
        """
        outputs: List[str] = []
        errors: List[str] = []
        stats: List[AsrStat] = []

        with ThreadPoolExecutor(max_workers=self.cfg.asr_max_workers) as ex:
            futures = [ex.submit(self._process_chunk, uri) for uri in chunk_uris]
            for fut in as_completed(futures):
                stat = fut.result()
                if stat["error"]:
                    errors.append(stat["error"])
                if stat["transcript"]:
                    outputs.append(stat["transcript"])
                stats.append(stat)
        return outputs, errors, stats

    def _process_chunk(self, uri: str) -> AsrStat:
        """チャンク1件をASRし、統計を返す。"""
        dest = f"s3://{self.cfg.bucket}/processed/{self.cfg.course_id}/transcript/raw/{Path(uri).stem}.txt"
        started = time.time()
        stat: AsrStat = {
            "chunk": uri,
            "transcript": None,
            "elapsed_ms": 0,
            "error": None,
            "avg_confidence": None,
        }
        try:
            self._last_avg_confidence = None
            text = self._transcribe_with_retry(uri)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
                tmp_path = tmp.name
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write(text.strip() + "\n")
                self.s3.upload_file(tmp_path, dest)
                stat["transcript"] = dest
            finally:
                try:
                    os.remove(tmp_path)
                except FileNotFoundError:
                    pass
        except Exception as e:  # noqa: BLE001
            stat["error"] = f"ASR failed: {uri} ({e})"
        stat["elapsed_ms"] = int((time.time() - started) * 1000)
        # faster-whisperの場合、直近の平均信頼度を拾う
        if hasattr(self, "_last_avg_confidence"):
            stat["avg_confidence"] = getattr(self, "_last_avg_confidence")
        return stat

    def _transcribe_with_retry(self, uri: str) -> str:
        """リトライ付きでASR実行。"""
        last_err: Exception | None = None
        for attempt in range(1, self.cfg.asr_max_retries + 2):
            try:
                return self._transcribe_uri(uri)
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt <= self.cfg.asr_max_retries:
                    time.sleep(1.0)
                    continue
                raise e
        raise last_err or RuntimeError("ASR failed without exception?")

    def _transcribe_uri(self, uri: str) -> str:
        """ASRを実行して文字列を返す。"""
        with self.s3.temp_local_copy(uri) as local_path:
            if self.cfg.asr_mode == "whisper":
                return self._run_whisper(local_path)
            if self.cfg.asr_mode == "faster-whisper":
                return self._run_faster_whisper(local_path)
            raise ValueError(f"未知のasr_mode: {self.cfg.asr_mode}")

    def _run_whisper(self, audio_path: str) -> str:
        """whisper公式実装で文字起こしする。"""
        try:
            import whisper
        except ImportError as e:
            raise ImportError("whisper がインストールされていません。pip install openai-whisper を実行してください。") from e

        model_name = self.model_path or self.cfg.asr_model
        model = whisper.load_model(model_name)
        result = model.transcribe(audio_path)
        segments = result.get("segments", [])
        confidences = []
        for seg in segments:
            logprob = seg.get("avg_logprob")
            if logprob is not None:
                confidences.append(min(1.0, max(0.0, float(pow(2.71828, logprob)))))
        self._last_avg_confidence = sum(confidences) / len(confidences) if confidences else None
        return result.get("text", "")

    def _run_faster_whisper(self, audio_path: str) -> str:
        """faster-whisperで文字起こしする。"""
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise ImportError("faster-whisper がインストールされていません。pip install faster-whisper を実行してください。") from e

        model_name = self.model_path or self.cfg.asr_model
        # compute_typeを指定（CPU時の安定性確保）
        model = WhisperModel(model_name, compute_type="auto")
        segments, info = model.transcribe(audio_path)
        texts = []
        confidences = []
        for seg in segments:
            texts.append(seg.text)
            if seg.avg_logprob is not None:
                # logprob -> rough confidence (0-1に寄せるためexp)
                confidences.append(min(1.0, max(0.0, float(pow(2.71828, seg.avg_logprob)))))
        if confidences:
            avg_conf = sum(confidences) / len(confidences)
            # 後段でstatに入れるために返り値と別に保持したいが、型変更を避けるため属性に置く
            self._last_avg_confidence = avg_conf
        else:
            self._last_avg_confidence = None
        return "\n".join(texts)
