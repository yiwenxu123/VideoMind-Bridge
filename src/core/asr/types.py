"""ASR 统一类型（阶段 1）

定义转录链路对外只暴露的数据结构：音频引用、转写选项、转录结果、
后端能力声明，以及错误层级。适配器只负责翻译厂商差异，不向上泄露
各自的 metadata 形状。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import CostTier


class AsrError(Exception):
    """ASR 链路异常基类"""

    code = "asr_error"


class AsrConfigError(AsrError):
    """注册表/配置层面的错误（未知后端、链为空等）"""

    code = "asr_config_error"


class AsrUnavailable(AsrError):
    """后端不可用：缺依赖、缺密钥、缺运行时"""

    code = "asr_unavailable"


class AsrInputError(AsrError):
    """输入不满足后端要求（如需要本地文件却只给了 URL）"""

    code = "asr_input_error"


class AsrFailed(AsrError):
    """后端执行失败（网络、厂商报错、解码失败等）"""

    code = "asr_failed"


class AsrEmpty(AsrError):
    """后端执行成功但结果为空"""

    code = "asr_empty"


class AsrChainError(AsrError):
    """降级链全部失败，携带每一次尝试的摘要"""

    code = "asr_chain_failed"

    def __init__(self, attempts: list[dict[str, Any]]) -> None:
        self.attempts = attempts
        detail = "; ".join(
            f"{a.get('provider', '?')}: {a.get('status', 'error')}"
            f"{(' - ' + str(a.get('message'))) if a.get('message') else ''}"
            for a in attempts
        )
        super().__init__(detail or "所有 ASR 后端均不可用")
        self.message = detail


@dataclass
class MediaRef:
    """音频引用：本地临时文件与（可选）公网 URL。

    本地文件是当前所有提取器的既有产物；公网 URL 留给未来只接受 URL
    的云端后端。适配器通过 capabilities().requires_public_url 声明需求。
    """

    path: Path | None = None
    url: str | None = None
    mime_type: str | None = None

    def require_path(self) -> Path:
        if self.path is None:
            raise AsrInputError("该 ASR 后端需要本地音频文件，但未提供 path")
        return self.path


@dataclass
class TranscribeOptions:
    """单次转写选项（阶段 2 接入请求级覆盖与成本上限）"""

    language: str | None = None
    timestamps: bool = True
    max_duration_sec: float | None = None
    max_cost: CostTier | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def parse_cost_tier(value: str | CostTier | None) -> CostTier | None:
    """把配置/请求里的成本档位字符串转成 CostTier；非法值返回 None。"""
    if value is None:
        return None
    if isinstance(value, CostTier):
        return value
    try:
        return CostTier(str(value).strip().lower())
    except ValueError:
        return None


@dataclass(frozen=True)
class Segment:
    """统一时间轴分段"""

    start: float
    end: float
    text: str
    speaker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"start": self.start, "end": self.end, "text": self.text}
        if self.speaker:
            data["speaker"] = self.speaker
        return data


@dataclass
class Transcript:
    """统一转录结果（所有后端都必须产出这个形状）"""

    text: str
    provider: str = ""
    model: str = ""
    model_version: str = ""
    language: str | None = None
    segments: list[Segment] | None = None
    duration_seconds: float = 0.0
    cost_tier: CostTier = CostTier.CHEAP
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "language": self.language,
            "cost_tier": self.cost_tier.value,
        }
        if self.model_version:
            data["model_version"] = self.model_version
        if self.segments:
            data["segments"] = [s.to_dict() for s in self.segments]
        if self.duration_seconds:
            data["duration_seconds"] = self.duration_seconds
        if self.metadata:
            data["metadata"] = self.metadata
        return data


@dataclass
class Capabilities:
    """后端能力声明：供 /capabilities 与调度使用，探测时不得加载模型"""

    name: str
    available: bool
    languages: list[str] = field(default_factory=list)
    timestamps: bool = False
    requires_public_url: bool = False
    max_duration_sec: float | None = None
    cost_tier: CostTier = CostTier.CHEAP
    model: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "available": self.available,
            "languages": self.languages,
            "timestamps": self.timestamps,
            "requires_public_url": self.requires_public_url,
            "max_duration_sec": self.max_duration_sec,
            "cost_tier": self.cost_tier.value,
            "model": self.model,
        }
        if self.notes:
            data["notes"] = self.notes
        return data
