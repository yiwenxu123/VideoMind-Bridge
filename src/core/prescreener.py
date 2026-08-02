"""内容预筛引擎

流程: URL → 平台检测 → (可选)元信息获取 → 规则评分 → 分级

两套分级:
- 内容基本面: SEO/时长/营销规则评分 (grade/score, 向后兼容)
- 提取成本决策: 平台/字幕/时长成本规则 (cost_grade/recommended_cost_tier)
  回答"提取这个链接要花多少钱", 供路由直接消费。

两阶段模式:
- quick (< 2ms): 仅 URL 分析, 无网络
- full (< 5s):   通过提取器获取标题+时长后完整评分
"""

from __future__ import annotations

import logging

from .models import ContentGrade, PrescreenResult
from .prescreen_rules import (
    apply_cost_rules,
    build_skip_reason,
    cost_tier_for_grade,
    run_all_rules,
)
from .router import ContentRouter

logger = logging.getLogger(__name__)

def detect_platform(url: str) -> str:
    """从 URL 检测平台 (纯规则, 无网络)"""
    from ..utils.platform_detector import detect_platform as _detect_platform
    return _detect_platform(url)


class Prescreener:
    """内容预筛引擎"""

    def __init__(self, router: ContentRouter | None = None) -> None:
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
            PrescreenResult: 预筛结果 (含基本面分级 + 提取成本决策)
        """
        platform = detect_platform(url)
        score, grade, reasons = run_all_rules(title, duration_seconds, platform)
        cost_grade, cost_reasons = apply_cost_rules(platform, duration_seconds)

        return PrescreenResult(
            url=url,
            platform=platform,
            title=title,
            duration_seconds=duration_seconds,
            grade=ContentGrade(grade),
            score=round(score, 1),
            reasons=reasons,
            cost_grade=ContentGrade(cost_grade),
            recommended_cost_tier=cost_tier_for_grade(cost_grade),
            skip_reason=build_skip_reason(cost_grade, platform),
            metadata={
                "has_title": bool(title),
                "has_duration": duration_seconds > 0,
                "cost_reasons": cost_reasons,
            },
        )

    def prescreen_quick(self, url: str) -> PrescreenResult:
        """纯 URL 预筛 (无网络, < 2ms)

        仅基于 URL 和平台特征做极简判断, 不获取任何元信息。
        """
        platform = detect_platform(url)
        cost_grade, _ = apply_cost_rules(platform, 0.0)

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
            cost_grade=ContentGrade(cost_grade),
            recommended_cost_tier=cost_tier_for_grade(cost_grade),
            skip_reason=build_skip_reason(cost_grade, platform),
            metadata={
                "prescreen_mode": "quick",
                "has_title": False,
                "cost_reasons": [f"平台 {platform}: 零 Cookie 提取" if platform in ("bilibili", "youtube", "douyin", "xiaohongshu") else f"平台 {platform}: 需兜底通道"],
            },
        )

    def is_extraction_worthwhile(self, grade: ContentGrade, min_grade: ContentGrade = ContentGrade.C) -> bool:
        """判断是否值得提取 (基于成本分级)

        默认 C 级以上值得提取 (B/A/S 有价值, C/D 需谨慎)
        """
        grade_order = {
            ContentGrade.S: 4, ContentGrade.A: 3,
            ContentGrade.B: 2, ContentGrade.C: 1, ContentGrade.D: 0,
        }
        return grade_order.get(grade, 0) >= grade_order.get(min_grade, 1)

    def recommend_cost_tier(self, grade: ContentGrade) -> str:
        """根据成本分级推荐提取成本

        与 cost_tier_for_grade 一致, 供旧调用方使用。
        """
        recommendations = {
            ContentGrade.S: "free",
            ContentGrade.A: "free",
            ContentGrade.B: "cheap",
            ContentGrade.C: "paid",
            ContentGrade.D: "paid",
        }
        return recommendations.get(grade, "free")
