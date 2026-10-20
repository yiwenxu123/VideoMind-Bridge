"""Transcript → ExtractResult 映射（阶段 1）

三个调用点不再各自拼结果：统一在这里写入 content/language/segments
与 metadata。保留 api_provider/model 旧键，避免已有调用方（含文档示例）
读取不到；新键 asr_provider/asr_model/asr_attempts 供基础设施契约使用。
"""

from __future__ import annotations

from typing import Any

from ..models import CostTier, ExtractResult
from .types import Transcript

_LEGACY_PROVIDER = {
    "faster-whisper": "faster_whisper",
    "dashscope": "dashscope_asr",
    "aliyun": "aliyun_asr",
    "sensevoice": "sensevoice_asr",
}


def transcript_to_extract_result(
    transcript: Transcript,
    *,
    url: str,
    platform: str,
    title: str,
    source: str,
    cost_tier: CostTier,
    duration_seconds: float = 0.0,
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> ExtractResult:
    legacy_provider = _LEGACY_PROVIDER.get(transcript.provider, transcript.provider)
    meta: dict[str, Any] = {
        "asr_provider": transcript.provider,
        "asr_model": transcript.model,
        "api_provider": legacy_provider,
        "model": transcript.model,
    }
    if transcript.model_version:
        meta["asr_model_version"] = transcript.model_version
    if transcript.metadata.get("attempts"):
        meta["asr_attempts"] = transcript.metadata["attempts"]
    if transcript.metadata.get("elapsed_seconds") is not None:
        meta["asr_elapsed_seconds"] = transcript.metadata["elapsed_seconds"]
    if description:
        meta["description"] = description
    if metadata:
        meta.update(metadata)

    return ExtractResult(
        success=True,
        platform=platform,
        title=title,
        content=transcript.text,
        source=source,
        url=url,
        cost_tier=cost_tier,
        duration_seconds=duration_seconds or transcript.duration_seconds,
        language=transcript.language,
        segments=[s.to_dict() for s in transcript.segments] if transcript.segments else None,
        metadata=meta,
    )
