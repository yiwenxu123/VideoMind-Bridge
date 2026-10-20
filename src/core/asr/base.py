"""ASR 后端抽象（阶段 1）

Transcriber 是链路唯一的扩展点：新增/替换音频模型 = 新增一个适配器，
不动平台提取器、不动调用方。约束：
- __init__ 必须轻量，不加载模型、不读密钥；密钥与依赖检查放 capabilities()
- transcribe() 只接收 MediaRef + TranscribeOptions，只返回 Transcript
- 失败抛 AsrError 子类，由 chain 决定是否降级
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .types import Capabilities, MediaRef, TranscribeOptions, Transcript


def resolve_extractor_key(name: str) -> str | None:
    """读取提取器密钥：环境变量 > 密钥环（与 ContentExtractor 同源）。"""
    from ...services.config_manager import get_config_manager

    return get_config_manager().get_extractor_key(name)


class Transcriber(ABC):
    """ASR 后端协议实现基类"""

    name: str = ""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})

    @abstractmethod
    def capabilities(self) -> Capabilities:
        """返回能力与可用性；不得加载模型、不得发起网络请求。"""

    def is_available(self) -> bool:
        return self.capabilities().available

    @abstractmethod
    def transcribe(self, media: MediaRef, options: TranscribeOptions) -> Transcript:
        """执行转写；失败抛 AsrError 子类。"""
