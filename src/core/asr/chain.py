"""ASR 降级链（阶段 1）

统一语义（对齐现有三条调用路径的既有行为）：
- 后端不可用 → 跳过，不调用
- 抛异常 → 记录，换下一个
- 返回空文本 → 记录 empty，换下一个
- 第一个非空结果返回，并把失败尝试写进 transcript.metadata["attempts"]
- 全部失败 → AsrChainError，携带每次尝试摘要

Stage 1 不做自动重试；默认链与现有行为一致（本地 whisper → DashScope）。
"""

from __future__ import annotations

import os
import time
from typing import Any

from .registry import create_transcriber
from .types import (
    AsrChainError,
    AsrConfigError,
    AsrError,
    MediaRef,
    TranscribeOptions,
    Transcript,
)

DEFAULT_CHAIN = ["faster_whisper", "dashscope"]


def resolve_chain(chain: list[str] | None = None) -> list[str]:
    """解析降级链：显式参数 > VMB_ASR_CHAIN 环境变量 > 默认链。

    显式传入空列表视为配置错误（返回空链，由调用方报 AsrChainError）。
    """
    if chain is not None:
        return [name for name in chain if name]
    env_chain = os.getenv("VMB_ASR_CHAIN", "").strip()
    if env_chain:
        return [name.strip() for name in env_chain.split(",") if name.strip()]
    return list(DEFAULT_CHAIN)


def transcribe_with_chain(
    media: MediaRef,
    options: TranscribeOptions | None = None,
    chain: list[str] | None = None,
    backend_configs: dict[str, dict[str, Any]] | None = None,
) -> Transcript:
    """按链执行转写，返回第一个非空结果。"""
    names = resolve_chain(chain)
    if not names:
        raise AsrChainError([])
    opts = options or TranscribeOptions()
    attempts: list[dict[str, Any]] = []

    for name in names:
        try:
            backend = create_transcriber(name, (backend_configs or {}).get(name))
        except AsrConfigError as exc:
            attempts.append({"provider": name, "status": "config_error", "message": str(exc)})
            continue

        if not backend.is_available():
            attempts.append({"provider": name, "status": "unavailable"})
            continue

        started = time.perf_counter()
        try:
            transcript = backend.transcribe(media, opts)
        except AsrError as exc:
            attempts.append(
                {
                    "provider": name,
                    "status": exc.code,
                    "message": str(exc),
                    "elapsed_seconds": round(time.perf_counter() - started, 2),
                }
            )
            continue
        except Exception as exc:  # 适配器未包装的意外异常也要降级而非炸链
            attempts.append(
                {
                    "provider": name,
                    "status": "unexpected_error",
                    "message": str(exc),
                    "elapsed_seconds": round(time.perf_counter() - started, 2),
                }
            )
            continue

        elapsed = round(time.perf_counter() - started, 2)
        if not (transcript.text or "").strip():
            attempts.append({"provider": name, "status": "empty", "elapsed_seconds": elapsed})
            continue

        transcript.metadata["attempts"] = attempts
        transcript.metadata["elapsed_seconds"] = elapsed
        return transcript

    raise AsrChainError(attempts)
