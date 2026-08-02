"""faster-whisper 本地转写共享调用（bilibili/tikhub/ytdlp_asr 复用）

模型懒加载并缓存为进程级单例, 避免重复加载。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_MODEL: Any = None
_MODEL_SIZE: str = ""


def transcribe_local(
    audio_path: Path,
    language: str = "zh",
    model_size: str = "base",
) -> tuple[str, list[dict] | None]:
    """使用 faster-whisper 本地转写音频。

    Returns:
        (text, segments): 转录文本与时间轴分段, 无分段时为 None

    Raises:
        ImportError: faster-whisper 未安装
        RuntimeError: 转写失败
    """
    global _MODEL, _MODEL_SIZE

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ImportError("faster-whisper 未安装 (pip install faster-whisper)")

    if _MODEL is None or model_size != _MODEL_SIZE:
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        _MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
        _MODEL_SIZE = model_size

    segments_iter, info = _MODEL.transcribe(str(audio_path), language=language)

    text_parts: list[str] = []
    segment_list: list[dict] = []
    for seg in segments_iter:
        text_parts.append(seg.text)
        segment_list.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
        })

    text = " ".join(text_parts).strip()
    return text, (segment_list or None)
