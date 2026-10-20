"""统一 ASR 能力包（阶段 1）

对外入口：
- transcribe_with_chain / resolve_chain：降级链执行
- transcript_to_extract_result：结果映射
- available_transcribers / create_transcriber：能力发现与按需实例化
- 类型与错误层级：Transcript / Capabilities / AsrError 等
"""

from __future__ import annotations

from . import adapters  # noqa: E402,F401  触发后端注册
from .base import Transcriber, resolve_extractor_key
from .chain import (
    DEFAULT_CHAIN,
    resolve_chain,
    resolve_language,
    resolve_max_cost,
    transcribe_with_chain,
    validate_configured_chain,
)
from .normalizer import transcript_to_extract_result
from .registry import (
    available_transcribers,
    create_transcriber,
    get_transcriber_class,
    list_transcriber_names,
    register_transcriber,
    validate_chain,
)
from .types import (
    AsrChainError,
    AsrConfigError,
    AsrEmpty,
    AsrError,
    AsrFailed,
    AsrInputError,
    AsrUnavailable,
    Capabilities,
    MediaRef,
    Segment,
    TranscribeOptions,
    Transcript,
    parse_cost_tier,
)

__all__ = [
    "AsrChainError",
    "AsrConfigError",
    "AsrEmpty",
    "AsrError",
    "AsrFailed",
    "AsrInputError",
    "AsrUnavailable",
    "Capabilities",
    "DEFAULT_CHAIN",
    "MediaRef",
    "Segment",
    "Transcript",
    "Transcriber",
    "TranscribeOptions",
    "available_transcribers",
    "create_transcriber",
    "get_transcriber_class",
    "list_transcriber_names",
    "parse_cost_tier",
    "register_transcriber",
    "resolve_chain",
    "resolve_extractor_key",
    "resolve_language",
    "resolve_max_cost",
    "transcribe_with_chain",
    "transcript_to_extract_result",
    "validate_chain",
    "validate_configured_chain",
]
