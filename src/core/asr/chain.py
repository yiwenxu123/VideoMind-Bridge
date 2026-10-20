"""ASR 降级链（阶段 1 建立，阶段 2 接入配置默认值与成本过滤）

统一语义（对齐现有三条调用路径的既有行为）：
- 后端不可用 → 跳过，不调用
- 超出成本上限 → 跳过
- 抛异常 → 记录，换下一个
- 返回空文本 → 记录 empty，换下一个
- 第一个非空结果返回，并把失败尝试写进 transcript.metadata["attempts"]
- 全部失败 → AsrChainError，携带每次尝试摘要

优先级：请求显式参数 > 环境变量 > 配置文件 > 代码默认值。
"""

from __future__ import annotations

import os
import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ..models import _COST_TIER_PRIORITY, CostTier
from .registry import create_transcriber, validate_chain
from .types import (
    AsrChainError,
    AsrConfigError,
    AsrError,
    MediaRef,
    TranscribeOptions,
    Transcript,
    parse_cost_tier,
)

if TYPE_CHECKING:
    from ...models.config import AsrConfig

DEFAULT_CHAIN = ["faster_whisper", "dashscope"]


def _config_defaults() -> AsrConfig | None:
    """读取配置文件 + 环境变量合并后的 ASR 配置；失败时返回 None。"""
    try:
        from ...services.config_manager import get_config_manager

        return get_config_manager().get_asr_config()
    except Exception:
        return None


def resolve_chain(chain: list[str] | None = None, cfg: AsrConfig | None = None) -> list[str]:
    """解析降级链：显式参数 > VMB_ASR_CHAIN > 配置文件 > 默认链。

    显式传入空列表视为配置错误（返回空链，由调用方报 AsrChainError）。
    """
    if chain is not None:
        return [name for name in chain if name]
    env_chain = os.getenv("VMB_ASR_CHAIN", "").strip()
    if env_chain:
        return [name.strip() for name in env_chain.split(",") if name.strip()]
    if cfg is None:
        cfg = _config_defaults()
    if cfg and cfg.chain:
        return list(cfg.chain)
    return list(DEFAULT_CHAIN)


def validate_configured_chain() -> list[str]:
    """校验配置文件/环境变量里的默认链，供 API/CLI 启动时快速失败。"""
    cfg = _config_defaults()
    names = list(cfg.chain) if cfg and cfg.chain else list(DEFAULT_CHAIN)
    validate_chain(names)
    return names


def resolve_language(
    explicit: str | None = None,
    *,
    default: str | None = None,
    cfg: AsrConfig | None = None,
) -> str | None:
    """语言优先级：请求 > VMB_ASR_LANGUAGE > 配置文件 > 调用方默认值。"""
    if explicit:
        return explicit
    if "VMB_ASR_LANGUAGE" in os.environ:
        return os.environ.get("VMB_ASR_LANGUAGE", "").strip() or None
    if cfg is None:
        cfg = _config_defaults()
    if cfg and cfg.language:
        return cfg.language
    return default


def resolve_max_cost(
    explicit: CostTier | None = None,
    *,
    cfg: AsrConfig | None = None,
) -> CostTier | None:
    """成本上限优先级：请求 > VMB_ASR_MAX_COST > 配置文件。"""
    if explicit is not None:
        return explicit
    env_cost = parse_cost_tier(os.getenv("VMB_ASR_MAX_COST", "").strip() or None)
    if env_cost is not None:
        return env_cost
    if cfg is None:
        cfg = _config_defaults()
    return parse_cost_tier(cfg.max_cost) if cfg else None


def transcribe_with_chain(
    media: MediaRef,
    options: TranscribeOptions | None = None,
    chain: list[str] | None = None,
    backend_configs: dict[str, dict[str, Any]] | None = None,
    default_language: str | None = None,
) -> Transcript:
    """按链执行转写，返回第一个非空结果。"""
    cfg = _config_defaults()
    names = resolve_chain(chain, cfg=cfg)
    if not names:
        raise AsrChainError([])
    opts = options or TranscribeOptions()
    effective_opts = replace(
        opts,
        language=resolve_language(opts.language, default=default_language, cfg=cfg),
    )
    max_cost = resolve_max_cost(opts.max_cost, cfg=cfg)
    if backend_configs is None:
        backend_configs = cfg.backend_configs() if cfg else {}
    attempts: list[dict[str, Any]] = []

    for name in names:
        try:
            backend = create_transcriber(name, backend_configs.get(name))
        except AsrConfigError as exc:
            attempts.append({"provider": name, "status": "config_error", "message": str(exc)})
            continue

        caps = backend.capabilities()
        if not caps.available:
            attempts.append({"provider": name, "status": "unavailable"})
            continue
        if max_cost is not None:
            allowed = _COST_TIER_PRIORITY.get(max_cost, 99)
            actual = _COST_TIER_PRIORITY.get(caps.cost_tier, 99)
            if actual > allowed:
                attempts.append(
                    {"provider": name, "status": "cost_exceeded", "cost_tier": caps.cost_tier.value}
                )
                continue

        started = time.perf_counter()
        try:
            transcript = backend.transcribe(media, effective_opts)
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
