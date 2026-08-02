"""v2 引擎核心测试

覆盖 prescreener, prescreen_rules, router, models, formatter.
所有测试为纯逻辑无网络。
"""


from src.core.formatter import HermesFormatter
from src.core.models import ContentGrade, CostTier
from src.core.prescreen_rules import (
    apply_cost_rules,
    apply_duration_rules,
    apply_marketing_rules,
    apply_seo_rules,
    build_skip_reason,
    compute_grade,
    run_all_rules,
)
from src.core.prescreener import Prescreener, detect_platform
from src.core.router import ContentRouter

# ============================================================
# Models
# ============================================================

def test_content_grade_order():
    """ContentGrade 等级顺序"""
    assert ContentGrade.S.value == "S"
    assert ContentGrade.A.value == "A"
    assert ContentGrade.B.value == "B"
    assert ContentGrade.C.value == "C"
    assert ContentGrade.D.value == "D"


def test_cost_tier_priority():
    from src.core.models import _COST_TIER_PRIORITY
    tiers = [CostTier.FREE, CostTier.CHEAP, CostTier.PAID, CostTier.EXPENSIVE, CostTier.PREMIUM]
    for i in range(len(tiers) - 1):
        prio_i = _COST_TIER_PRIORITY[tiers[i]]
        prio_j = _COST_TIER_PRIORITY[tiers[i + 1]]
        assert prio_i < prio_j, f"预期 {tiers[i]}({prio_i}) 优先于 {tiers[i+1]}({prio_j})"


# ============================================================
# Platform detection
# ============================================================

def test_detect_platform_bilibili():
    assert detect_platform("https://www.bilibili.com/video/BV1xx") == "bilibili"
    assert detect_platform("https://b23.tv/xxxxx") == "bilibili"


def test_detect_platform_youtube():
    assert detect_platform("https://www.youtube.com/watch?v=xxx") == "youtube"
    assert detect_platform("https://youtu.be/xxx") == "youtube"


def test_detect_platform_douyin():
    assert detect_platform("https://www.douyin.com/video/123") == "douyin"
    assert detect_platform("https://v.douyin.com/xxx") == "douyin"


def test_detect_platform_xiaohongshu():
    assert detect_platform("https://www.xiaohongshu.com/explore/123") == "xiaohongshu"
    assert detect_platform("https://xhslink.com/xxx") == "xiaohongshu"


def test_detect_platform_unknown():
    assert detect_platform("https://www.google.com") == "unknown"
    assert detect_platform("") == "unknown"


# ============================================================
# SEO rules
# ============================================================

def test_seo_empty_title():
    delta, reasons = apply_seo_rules("")
    assert delta == -20
    assert any("空" in r for r in reasons)


def test_seo_short_title():
    delta, reasons = apply_seo_rules("短")
    assert delta < 0
    assert any("过短" in r for r in reasons)


def test_seo_long_title():
    delta, reasons = apply_seo_rules("长" * 81)
    assert delta <= -5
    assert any("过长" in r for r in reasons)


def test_seo_clickbait():
    delta, reasons = apply_seo_rules("震惊！99%的人都不知道的秘密！")
    assert delta < 0
    assert any("标题党" in r for r in reasons)


def test_seo_quality_signals():
    delta, reasons = apply_seo_rules("Python 入门教程：完整指南与深度解析")
    assert delta > 0
    assert any("质量" in r or "信号" in r for r in reasons)


def test_seo_good_length():
    delta, reasons = apply_seo_rules("长度适中的标题示例")
    assert delta > 0
    assert any("适中" in r for r in reasons)


# ============================================================
# Duration rules
# ============================================================

def test_duration_zero():
    """时长为零时不应用规则"""
    delta, reasons = apply_duration_rules(0, "unknown")
    assert delta == 0
    assert len(reasons) == 0


def test_duration_too_short():
    delta, reasons = apply_duration_rules(5, "bilibili")
    assert delta == -20
    assert any("过短" in r for r in reasons)


def test_duration_short():
    delta, reasons = apply_duration_rules(60, "bilibili")  # 1分钟
    assert delta == -5
    assert any("偏短" in r for r in reasons)


def test_duration_ideal():
    delta, reasons = apply_duration_rules(600, "bilibili")  # 10分钟
    assert delta == 10
    assert any("最佳" in r for r in reasons)


def test_duration_acceptable():
    delta, reasons = apply_duration_rules(1800, "bilibili")  # 30分钟
    assert delta == 0
    assert any("可接受" in r for r in reasons)


def test_duration_too_long():
    delta, reasons = apply_duration_rules(7200, "bilibili")  # 2小时
    assert delta == -10
    assert any("过长" in r for r in reasons)


# ============================================================
# Marketing rules
# ============================================================

def test_marketing_no_detection():
    delta, reasons = apply_marketing_rules("正常视频标题")
    assert delta == 0
    assert len(reasons) == 0


def test_marketing_detected():
    delta, reasons = apply_marketing_rules("广告：限时特价促销")
    assert delta < 0
    assert any("推广" in r for r in reasons)


def test_marketing_test_video():
    delta, reasons = apply_marketing_rules("测试视频标题")
    assert delta < 0
    assert any("低质量" in r for r in reasons)


def test_marketing_empty_title():
    delta, reasons = apply_marketing_rules("")
    assert delta == 0
    assert len(reasons) == 0


# ============================================================
# Grading
# ============================================================

def test_grade_s():
    grade, desc = compute_grade(85)
    assert grade == "S"

def test_grade_a():
    assert compute_grade(70)[0] == "A"

def test_grade_b():
    assert compute_grade(55)[0] == "B"

def test_grade_c():
    assert compute_grade(40)[0] == "C"

def test_grade_d():
    assert compute_grade(0)[0] == "D"


# ============================================================
# Full prescreen pipeline
# ============================================================

def test_prescreen_high_quality():
    """高质量视频: 好的标题 + 合适时长 + 无营销"""
    score, grade, reasons = run_all_rules(
        "Python 入门教程：从零开始掌握编程基础",
        600,  # 10分钟
        "youtube",
    )
    assert grade in ("S", "A"), f"高质量视频预期 S/A, 实际 {grade} ({score})"


def test_prescreen_low_quality():
    """低质量视频: 空标题 + 过短时长 + 营销词"""
    score, grade, reasons = run_all_rules(
        "广告",
        5,
        "bilibili",
    )
    assert grade == "D", f"低质量视频预期 D, 实际 {grade} ({score})"


def test_prescreen_mid_quality():
    """中等质量: 短视频但标题尚可"""
    score, grade, reasons = run_all_rules(
        "生活中的小技巧",
        30,
        "douyin",
    )
    assert grade in ("B", "C"), f"中等质量预期 B/C, 实际 {grade} ({score})"


def test_short_title_not_double_penalized():
    """普通短标题 (≤5 字) 不应命中「纯括号标题」低质量规则 (回归: 正则过宽 bug)"""
    score, grade, reasons = run_all_rules(
        "学习",
        600,
        "bilibili",
    )
    # 短标题仅被「标题过短」扣 15 分, 不应被低质量规则再扣 20 分
    assert not any("低质量" in r for r in reasons), reasons


def test_bracket_only_title_is_low_quality():
    """纯括号标题 (【文案】) 应命中低质量规则"""
    score, grade, reasons = run_all_rules(
        "【】",
        600,
        "bilibili",
    )
    assert any("低质量" in r for r in reasons), reasons


# ============================================================
# Prescreener
# ============================================================

def test_prescreener_quick():
    p = Prescreener(None)
    result = p.prescreen_quick("https://www.bilibili.com/video/BV1xx")
    assert result.platform == "bilibili"
    assert result.grade == ContentGrade.B
    assert result.score == 55.0
    assert not result.title
    assert "quick" in str(result.metadata.get("prescreen_mode", ""))


def test_prescreener_full():
    p = Prescreener(None)
    result = p.prescreen(
        "https://www.youtube.com/watch?v=xxx",
        title="深度解析 AI 编程：2026 年开发者必读指南",
        duration_seconds=1200,
    )
    assert result.platform == "youtube"
    assert result.grade in (ContentGrade.S, ContentGrade.A)
    assert result.score > 70
    assert result.title


def test_is_extraction_worthwhile():
    p = Prescreener(None)
    assert p.is_extraction_worthwhile(ContentGrade.S, ContentGrade.C) is True
    assert p.is_extraction_worthwhile(ContentGrade.A, ContentGrade.C) is True
    assert p.is_extraction_worthwhile(ContentGrade.B, ContentGrade.C) is True
    assert p.is_extraction_worthwhile(ContentGrade.C, ContentGrade.C) is True
    assert p.is_extraction_worthwhile(ContentGrade.D, ContentGrade.C) is False


def test_recommend_cost_tier():
    p = Prescreener(None)
    # 成本决策语义: 免费平台字幕可得 → FREE; 需付费 ASR → PAID
    assert p.recommend_cost_tier(ContentGrade.S) == "free"
    assert p.recommend_cost_tier(ContentGrade.A) == "free"
    assert p.recommend_cost_tier(ContentGrade.B) == "cheap"
    assert p.recommend_cost_tier(ContentGrade.C) == "paid"
    assert p.recommend_cost_tier(ContentGrade.D) == "paid"


# ============================================================
# 提取成本决策规则 (v3)
# ============================================================

def test_cost_rules_bilibili_free():
    """B站: 零 Cookie + 官方字幕 + 适中时长 → 免费高分级"""
    grade, reasons = apply_cost_rules("bilibili", 600)
    assert grade in ("S", "A"), f"B站适中时长预期 S/A, 实际 {grade} ({reasons})"


def test_cost_rules_youtube_free():
    """YouTube: 预期有官方字幕 → 免费"""
    grade, reasons = apply_cost_rules("youtube", 3600)
    assert grade in ("S", "A", "B"), f"YouTube预期 S/A/B, 实际 {grade}"


def test_cost_rules_unknown_platform_low():
    """未知平台: 无法直接提取 → 需商业 API 兜底, 低分级"""
    grade, reasons = apply_cost_rules("unknown", 600)
    assert grade in ("C", "D"), f"unknown 平台预期 C/D, 实际 {grade} ({reasons})"


def test_cost_rules_short_duration_downgrade():
    """超短内容: 提取性价比低 → 降级"""
    grade, reasons = apply_cost_rules("bilibili", 10)
    assert grade in ("B", "C", "D"), f"超短视频预期降级, 实际 {grade}"


def test_cost_rules_long_without_subtitle_paid():
    """超长无字幕平台 (douyin): ASR 成本高 → 需付费"""
    grade, reasons = apply_cost_rules("douyin", 7200)
    assert grade in ("B", "C", "D"), f"超长无字幕预期 C/D, 实际 {grade}"


def test_cost_rules_skip_reason():
    """C/D 级应给出 skip_reason, S/A/B 级无"""
    assert build_skip_reason("S", "bilibili") is None
    assert build_skip_reason("B", "douyin") is None
    c_reason = build_skip_reason("C", "douyin")
    assert c_reason is not None and "付费" in c_reason
    d_reason = build_skip_reason("D", "unknown")
    assert d_reason is not None and "跳过" in d_reason


def test_prescreen_includes_cost_decision():
    """prescreen() 应输出成本决策字段 (cost_grade / recommended_cost_tier / skip_reason)"""
    p = Prescreener(None)
    result = p.prescreen(
        "https://www.bilibili.com/video/BV1xx411c7mD",
        title="Python 入门教程：从零开始掌握编程基础",
        duration_seconds=600,
    )
    assert result.cost_grade is not None
    assert result.recommended_cost_tier is not None
    assert result.effective_cost_grade() == result.cost_grade
    # B站适中时长 → 免费推荐
    assert result.recommended_cost_tier.value == "free"
    assert result.skip_reason is None


# ============================================================
# Hermes Formatter
# ============================================================

def test_format_prescreen_result():
    from src.core.models import PrescreenResult
    result = PrescreenResult(
        url="https://example.com/video",
        platform="bilibili",
        title="测试视频",
        duration_seconds=300.0,
        grade=ContentGrade.B,
        score=60.0,
        reasons=["评分 60/100 → B 级"],
    )
    formatted = HermesFormatter.format_prescreen_result(result)
    assert formatted["url"] == "https://example.com/video"
    assert formatted["grade"] == "B"
    assert formatted["score"] == 60.0


# ============================================================
# Router
# ============================================================

def test_router_list_extractors():
    router = ContentRouter()
    extractors = router.list_extractors()
    assert "bilibili" in extractors
    assert "youtube" in extractors
    assert "douyin" in extractors
    assert "xiaohongshu" in extractors
    assert "douyin" in extractors
    assert "ytdlp" in extractors


def test_router_url_unsupported():
    router = ContentRouter()
    result = router.extract("https://example.com/not-a-video")
    assert result.success is False
    assert result.error is not None


def test_router_get_extractor():
    router = ContentRouter()
    ext = router.get_extractor("bilibili")
    assert ext is not None
    assert ext.platform_name == "bilibili"
