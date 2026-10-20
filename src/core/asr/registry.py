"""ASR 后端注册表（阶段 1）

与提取器注册表同构，但只存类不存实例：能力探测与降级链按需实例化，
避免"注册一个重模型后端，每次请求都付初始化成本"的老问题。
"""

from __future__ import annotations

from typing import Any

from .base import Transcriber
from .types import AsrConfigError, Capabilities

_TRANSCRIBERS: dict[str, type[Transcriber]] = {}


def register_transcriber(name: str, cls: type[Transcriber]) -> None:
    _TRANSCRIBERS[name] = cls


def list_transcriber_names() -> list[str]:
    return sorted(_TRANSCRIBERS)


def get_transcriber_class(name: str) -> type[Transcriber]:
    cls = _TRANSCRIBERS.get(name)
    if cls is None:
        available = ", ".join(list_transcriber_names()) or "（空）"
        raise AsrConfigError(f"未知 ASR 后端: {name}；可用: {available}")
    return cls


def create_transcriber(name: str, config: dict[str, Any] | None = None) -> Transcriber:
    return get_transcriber_class(name)(config)


def validate_chain(names: list[str]) -> None:
    """校验链非空且后端均已注册；用于 API/CLI 的请求参数校验。"""
    if not names:
        raise AsrConfigError("ASR 链不能为空")
    unknown = [name for name in names if name not in _TRANSCRIBERS]
    if unknown:
        available = ", ".join(list_transcriber_names()) or "（空）"
        raise AsrConfigError(f"未知 ASR 后端: {', '.join(unknown)}；可用: {available}")


def available_transcribers() -> list[Capabilities]:
    """探测所有已注册后端的能力；单个后端探测失败不影响其他后端。"""
    result: list[Capabilities] = []
    for name in list_transcriber_names():
        try:
            result.append(create_transcriber(name).capabilities())
        except Exception as exc:  # 能力探测不该拖垮 /health 或 /capabilities
            result.append(Capabilities(name=name, available=False, notes=f"探测失败: {exc}"))
    return result
