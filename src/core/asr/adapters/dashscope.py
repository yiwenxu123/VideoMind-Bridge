"""DashScope paraformer-v2 适配器（逻辑迁移自 extractors/_dashscope_asr.py）

2026+ 接口：长音频转写须用异步任务（X-DashScope-Async: enable）+ file_urls，
旧 base64 内联同步接口已废弃（400 url error）。需要公网可访问 URL：
文件会经 VMB_MEDIA_DIR + VMB_PUBLIC_URL 暴露后交给 DashScope 拉取。

.m4s 容器 DashScope 不接受，会先用 ffmpeg 转 mp3（对齐原 B 站链路行为）。
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import httpx

from ...media import MediaTranscodeError, transcode_to_mp3
from ...models import CostTier
from ..base import Transcriber, resolve_extractor_key
from ..registry import register_transcriber
from ..types import (
    AsrEmpty,
    AsrFailed,
    AsrUnavailable,
    Capabilities,
    MediaRef,
    Segment,
    TranscribeOptions,
    Transcript,
)

DASHSCOPE_ASR_SUBMIT_URL = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
DASHSCOPE_ASR_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
DASHSCOPE_ASR_MODEL = "paraformer-v2"
_DEFAULT_POLL_INTERVAL = 3.0
_DEFAULT_MAX_POLLS = 120


def _transcribe_audio_url(
    audio_url: str,
    api_key: str,
    language_hints: list[str] | None = None,
    poll_interval: float = _DEFAULT_POLL_INTERVAL,
    max_polls: int = _DEFAULT_MAX_POLLS,
) -> tuple[str, list[dict] | None]:
    """通过公网音频 URL 转写 (paraformer-v2 异步任务)。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    payload = {
        "model": DASHSCOPE_ASR_MODEL,
        "input": {"file_urls": [audio_url]},
        "parameters": {"language_hints": language_hints or ["zh"]},
    }

    resp = httpx.post(DASHSCOPE_ASR_SUBMIT_URL, headers=headers, json=payload, timeout=60.0)
    resp.raise_for_status()
    task_id = resp.json().get("output", {}).get("task_id")
    if not task_id:
        raise RuntimeError("DashScope ASR 未返回 task_id")

    trans_url = None
    for _ in range(max_polls):
        time.sleep(poll_interval)
        r = httpx.get(
            DASHSCOPE_ASR_TASK_URL.format(task_id=task_id),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        r.raise_for_status()
        out = r.json().get("output", {})
        status = out.get("task_status", "")
        if status == "SUCCEEDED":
            results = out.get("results", [])
            if results:
                trans_url = (
                    results[0].get("transcription_url")
                    or (results[0].get("output", {}) or {}).get("transcription_url")
                )
            break
        if status in ("FAILED", "CANCELED"):
            raise RuntimeError(f"DashScope ASR 任务 {status}: {r.text[:200]}")
    else:
        raise RuntimeError("DashScope ASR 任务超时")

    if not trans_url:
        raise RuntimeError("DashScope ASR 任务成功但无结果 URL")

    result_data = httpx.get(trans_url, timeout=60.0).json()
    transcripts = result_data.get("transcripts") or []
    if not transcripts:
        raise RuntimeError("DashScope ASR 结果为空")

    t0 = transcripts[0]
    text = (t0.get("text") or "").strip()
    sentences = t0.get("sentences") or []
    segments = [
        {
            "start": s.get("begin_time", 0) / 1000,
            "end": s.get("end_time", 0) / 1000,
            "text": s.get("text", ""),
        }
        for s in sentences
        if s.get("text")
    ] or None
    return text, segments


def _transcribe_audio_data(
    audio_path: Path,
    api_key: str,
) -> tuple[str, list[dict] | None]:
    """转写本地音频文件（拷贝到媒体目录暴露公网 URL 后走异步任务）。"""
    media_dir = os.getenv("VMB_MEDIA_DIR", "")
    public_url = os.getenv("VMB_PUBLIC_URL", "")
    if not media_dir or not public_url:
        raise RuntimeError("DashScope 转写需要公网音频 URL: 请配置 VMB_MEDIA_DIR + VMB_PUBLIC_URL")

    dst = Path(media_dir) / f"asr_{int(time.time() * 1000)}.mp3"
    try:
        shutil.copy2(audio_path, dst)
        audio_url = f"{public_url.rstrip('/')}/media/{dst.name}"
        return _transcribe_audio_url(audio_url, api_key)
    finally:
        dst.unlink(missing_ok=True)


def _prepare_audio(audio_path: Path) -> tuple[Path, Path | None]:
    """返回 (可提交文件, 需清理的临时文件)。.m4s 先转 mp3。"""
    if audio_path.suffix.lower() != ".m4s":
        return audio_path, None
    dst = Path(f"{audio_path}.dashscope.mp3")
    try:
        transcode_to_mp3(audio_path, dst)
    except MediaTranscodeError as exc:
        raise AsrFailed(f"DashScope 需要 mp3，转码失败: {exc}") from exc
    return dst, dst


class DashScopeTranscriber(Transcriber):
    """DashScope paraformer-v2 云端后端（需 key + 公网 URL）"""

    name = "dashscope"

    def _api_key(self) -> str:
        key = self.config.get("api_key") or resolve_extractor_key("dashscope_key")
        return key.strip() if key and key.strip() else ""

    def capabilities(self) -> Capabilities:
        key_ready = bool(self._api_key())
        public_url_ready = bool(
            os.getenv("VMB_MEDIA_DIR", "").strip()
            and os.getenv("VMB_PUBLIC_URL", "").strip()
        )
        return Capabilities(
            name=self.name,
            available=key_ready and public_url_ready,
            languages=["zh"],
            timestamps=True,
            requires_public_url=True,
            cost_tier=CostTier.PAID,
            model=DASHSCOPE_ASR_MODEL,
            notes="需要 dashscope_key + VMB_MEDIA_DIR + VMB_PUBLIC_URL；.m4s 自动转 mp3",
        )

    def transcribe(self, media: MediaRef, options: TranscribeOptions) -> Transcript:
        api_key = self._api_key()
        if not api_key:
            raise AsrUnavailable("dashscope_key 未配置")
        audio_path = media.require_path()

        prepared, cleanup = _prepare_audio(audio_path)
        try:
            try:
                text, raw_segments = _transcribe_audio_data(prepared, api_key)
            except AsrFailed:
                raise
            except Exception as exc:
                raise AsrFailed(f"DashScope ASR 调用失败: {exc}") from exc
        finally:
            if cleanup is not None:
                cleanup.unlink(missing_ok=True)

        if not text:
            raise AsrEmpty("DashScope ASR 返回空转录")

        segments = [
            Segment(
                start=float(item.get("start", 0.0)),
                end=float(item.get("end", 0.0)),
                text=str(item.get("text", "")),
            )
            for item in (raw_segments or [])
        ]
        return Transcript(
            text=text,
            provider="dashscope",
            model=DASHSCOPE_ASR_MODEL,
            language=options.language or "zh",
            segments=segments or None,
            cost_tier=CostTier.PAID,
        )


register_transcriber("dashscope", DashScopeTranscriber)
