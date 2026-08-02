"""DashScope paraformer-v2 语音识别共享调用（tikhub/ytdlp_asr 复用）"""

from __future__ import annotations

import base64
from pathlib import Path

import httpx

DASHSCOPE_ASR_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/audio/transcription/asr"
DASHSCOPE_ASR_MODEL = "paraformer-v2"


def transcribe_audio_data(
    audio_path: Path,
    api_key: str,
    timeout: float = 180.0,
) -> tuple[str, list[dict] | None]:
    """调用 DashScope paraformer-v2 转录音频。

    Returns:
        (text, segments): 转录文本与时间轴分段（无分段时为 None）

    Raises:
        httpx.HTTPError: 网络/HTTP 错误
        Exception: 解析或读取失败
    """
    audio_b64 = base64.b64encode(audio_path.read_bytes()).decode()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DASHSCOPE_ASR_MODEL,
        "input": {"audio_data": audio_b64},
    }

    resp = httpx.post(
        DASHSCOPE_ASR_ENDPOINT,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()

    output = data.get("output", {})
    text = output.get("text", "") or output.get("transcript", "") or ""
    segments_raw = output.get("sentences", output.get("segments", []))

    segments = [
        {
            "start": s.get("begin_time", s.get("start", 0)) / 1000,
            "end": s.get("end_time", s.get("end", 0)) / 1000,
            "text": s.get("text", ""),
        }
        for s in segments_raw
        if s.get("text")
    ] if isinstance(segments_raw, list) else None

    return text, segments
