"""核心数据模型"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ContentGrade(Enum):
    """内容质量等级 (预筛结果)

    等级含义:
    - S: 必须提取 — 高价值内容
    - A: 建议提取
    - B: 值得提取
    - C: 低优先级
    - D: 跳过 — 不值得提取
    """

    S = "S"
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class CostTier(Enum):
    """提取成本等级 (用于路由决策)"""

    FREE = "free"          # 直接 API, 零成本
    CHEAP = "cheap"        # Coze (有 Token 时), 低成本
    PAID = "paid"          # 付费 API
    EXPENSIVE = "expensive"  # Whisper 本地 ASR (消耗 CPU/GPU)
    PREMIUM = "premium"    # 高级商业 API


# 成本等级优先级 (数字越小越优先)
_COST_TIER_PRIORITY = {
    CostTier.FREE: 0,
    CostTier.CHEAP: 1,
    CostTier.PAID: 2,
    CostTier.EXPENSIVE: 3,
    CostTier.PREMIUM: 4,
}


@dataclass
class PlatformInfo:
    """平台检测结果"""

    platform: str  # bilibili / youtube / douyin / xiaohongshu / unknown
    url: str       # 标准化后的 URL
    video_id: str  # 提取的视频 ID
    raw_url: str = ""  # 原始 URL


@dataclass
class PrescreenResult:
    """内容预筛结果"""

    url: str
    platform: str
    title: str = ""
    duration_seconds: float = 0.0
    grade: ContentGrade = ContentGrade.C
    score: float = 50.0  # 0-100
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractorMetadata:
    """提取器元信息"""

    name: str
    platform: str
    cost_tier: CostTier
    available: bool
    supported: bool = False


@dataclass
class ExtractResult:
    """内容提取结果"""

    success: bool
    platform: str
    title: str
    content: str           # 完整文本内容 (字幕/转录)
    source: str            # 使用的提取器名称
    url: str
    cost_tier: CostTier
    duration_seconds: float = 0.0  # 视频时长(秒)
    language: str | None = None
    segments: list[dict[str, Any]] | None = None  # 字幕片段
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转为字典 (Hermes 兼容)"""
        d: dict[str, Any] = {
            "success": self.success,
            "platform": self.platform,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "url": self.url,
            "cost_tier": self.cost_tier.value,
            "duration_seconds": self.duration_seconds,
        }
        if self.language:
            d["language"] = self.language
        if self.segments:
            d["segments"] = self.segments
        if self.metadata:
            d["metadata"] = self.metadata
        if self.error:
            d["error"] = self.error
        return d
