"""VideoMind Bridge v2 核心引擎

分层架构:
- models: 数据模型 (PrescreenResult, ExtractResult, ContentGrade, CostTier)
- prescreener: 内容预筛引擎
- prescreen_rules: SEO/时长/营销/原创性规则
- router: 成本感知路由 (优先级列表遍历)
- formatter: Hermes 兼容输出格式化
- extractors/: 各平台提取器 (基类 + 平台实现)
"""

from .models import (
    ContentGrade,
    CostTier,
    PlatformInfo,
    PrescreenResult,
    ExtractResult,
    ExtractorMetadata,
)
from .router import ContentRouter
from .formatter import HermesFormatter
from .prescreener import Prescreener

__all__ = [
    "ContentGrade",
    "CostTier",
    "PlatformInfo",
    "PrescreenResult",
    "ExtractResult",
    "ExtractorMetadata",
    "ContentRouter",
    "HermesFormatter",
    "Prescreener",
]
