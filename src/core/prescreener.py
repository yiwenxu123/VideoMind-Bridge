"""内容预筛引擎

流程: URL → 平台检测 → (可选)元信息获取 → 规则评分 → 分级

两阶段模式:
- quick (< 2ms): 仅 URL 分析, 无网络
- full (< 5s):   通过提取器获取标题+时长后完整评分
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .models import ContentGrade, PrescreenResult
from .prescreen_rules import GRADE_THRESHOLDS, run_all_rules
from .router import ContentRouter

logger = logging.getLogger(__name__)

# URL → 平台映射
_PLATFORM_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("bilibili", re.compile(r"(bilibili\.com|b23\.tv)")),
    ("youtube", re.compile(r"(youtube\.com|youtu\.be)")),
    ("douyin", re.compile(r"(douyin\.com|iesdouyin\.com|v\.douyin\.com)")),
    ("xiaohongshu", re.compile(r"(xiaohongshu\.com|xhslink\.com)")),
]


def detect_platform(url: str) -> str:
    """从 URL 检测平台 (纯规则, 无网络)

    Returns:
        platform name or "unknown"
    """
    for name, pattern in _PLATFORM_PATTERNS:
        if pattern.search(url):
            return name
    return "unknown"


class Prescreener:
    """内容预筛引擎"""

    def __init__(self, router: Optional[ContentRouter] = None) -> None:
        self._router = router or ContentRouter()

    def prescreen(
        self,
        url: str,
        title: str = "",
        duration_seconds: float = 0.0,
    ) -> PrescreenResult:
        """执行内容预筛 (纯规则, 无网络请求)

        Args:
            url: 视频 URL
            title: 视频标题 (建议传入, 否则仅做平台级别分析)
            duration_seconds: 视频时长 (建议传入, 否则仅做平台级别分析)

        Returns:
            PrescreenResult: 预筛结果
        """
        platform = detect_platform(url)
        score, grade, reasons = run_all_rules(title, duration_seconds, platform)

        return PrescreenResult(
            url=url,
            platform=platform,
            title=title,
            duration_seconds=duration_seconds,
            grade=ContentGrade(grade),
            score=round(score, 1),
            reasons=reasons,
            metadata={
                "has_title": bool(title),
                "has_duration": duration_seconds > 0,
            },
        )

    def prescreen_quick(self, url: str) -> PrescreenResult:
        """纯 URL 预筛 (无网络, < 2ms)

        仅基于 URL 和平台特征做极简判断, 不获取任何元信息。
        """
        platform = detect_platform(url)
        return PrescreenResult(
            url=url,
            platform=platform,
            title="",
            duration_seconds=0.0,
            grade=ContentGrade.B,  # 无信息时给中等等级
            score=55.0,
            reasons=[
                f"平台: {platform}",
                "快速预筛模式 — 未获取元信息, 默认 B 级",
                "执行 --smart 或提供标题可获得更准确评分",
            ],
            metadata={"prescreen_mode": "quick", "has_title": False},
        )

    def is_extraction_worthwhile(self, grade: ContentGrade, min_grade: ContentGrade = ContentGrade.C) -> bool:
        """判断是否值得提取

        默认 C 级以上值得提取 (B/A/S 有价值, C/D 需谨慎)
        """
        grade_order = {
            ContentGrade.S: 4, ContentGrade.A: 3,
            ContentGrade.B: 2, ContentGrade.C: 1, ContentGrade.D: 0,
        }
        return grade_order.get(grade, 0) >= grade_order.get(min_grade, 1)

    def recommend_cost_tier(self, grade: ContentGrade) -> str:
        """根据等级推荐提取成本"""
        recommendations = {
            ContentGrade.S: "paid",
            ContentGrade.A: "paid",
            ContentGrade.B: "free",
            ContentGrade.C: "free",
            ContentGrade.D: "free",
        }
        return recommendations.get(grade, "free")
