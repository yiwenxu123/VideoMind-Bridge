"""DashScope paraformer-v2 语音识别共享调用（bilibili/ytdlp_asr/tikhub 复用）

2026+ 接口: 长音频转写须用异步任务 (X-DashScope-Async: enable) + file_urls,
旧 base64 内联同步接口已废弃 (400 url error)。
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import httpx

DASHSCOPE_ASR_SUBMIT_URL = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
DASHSCOPE_ASR_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
DASHSCOPE_ASR_MODEL = "paraformer-v2"
_DEFAULT_POLL_INTERVAL = 3.0
_DEFAULT_MAX_POLLS = 120


def transcribe_audio_url(
    audio_url: str,
    api_key: str,
    language_hints: list[str] | None = None,
    poll_interval: float = _DEFAULT_POLL_INTERVAL,
    max_polls: int = _DEFAULT_MAX_POLLS,
) -> tuple[str, list[dict] | None]:
    """通过公网音频 URL 转写 (paraformer-v2 异步任务)。

    Returns:
        (text, segments): 转录文本与时间轴分段 (毫秒转秒), 无分段时为 None

    Raises:
        httpx.HTTPError: 网络/HTTP 错误
        RuntimeError: 任务失败/超时
    """
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


def transcribe_audio_data(
    audio_path: Path,
    api_key: str,
    timeout: float = 300.0,
) -> tuple[str, list[dict] | None]:
    """转写本地音频文件。

    需要公网可访问 URL (DashScope 拉取): 将文件放入媒体目录
    (env VMB_MEDIA_DIR + VMB_PUBLIC_URL) 后调用异步转写。

    Returns:
        (text, segments)

    Raises:
        RuntimeError: 未配置公网 URL 或媒体目录
        httpx.HTTPError / RuntimeError: 转写失败
    """
    media_dir = os.getenv("VMB_MEDIA_DIR", "")
    public_url = os.getenv("VMB_PUBLIC_URL", "")
    if not media_dir or not public_url:
        raise RuntimeError(
            "DashScope 转写需要公网音频 URL: 请配置 VMB_MEDIA_DIR + VMB_PUBLIC_URL"
        )

    dst = Path(media_dir) / f"asr_{int(time.time() * 1000)}.mp3"
    try:
        import shutil

        shutil.copy2(audio_path, dst)
        audio_url = f"{public_url.rstrip('/')}/media/{dst.name}"
        return transcribe_audio_url(audio_url, api_key)
    finally:
        dst.unlink(missing_ok=True)
