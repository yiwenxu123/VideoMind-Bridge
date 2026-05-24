"""预筛规则引擎

纯规则, 无网络请求。每条规则返回 (score_delta: int, reasons: list[str])。

评分体系: 基础分 50, 每条规则 +/- 分数, 最终 0-100。
等级阈值: S≥85, A≥70, B≥55, C≥40, D<40
"""

from __future__ import annotations

import re

# ============================================================
# 平台最佳时长 (秒)
# ============================================================
PLATFORM_IDEAL_DURATION: dict[str, tuple[int, int, int]] = {
    # (min_good, max_good, max_acceptable)
    "bilibili":      (300, 1200, 3600),     # 5-20分钟最佳
    "youtube":       (480, 2400, 7200),     # 8-40分钟最佳
    "douyin":        (15, 120, 600),         # 15秒-2分钟最佳
    "xiaohongshu":   (30, 180, 600),         # 30秒-3分钟最佳
    "unknown":       (60, 600, 3600),
}

# ============================================================
# SEO 信号
# ============================================================

# 标题过短 (< 8 字)
_TITLE_TOO_SHORT = re.compile(r"^.{1,7}$")

# 震惊体关键词
_CLICKBAIT_WORDS = [
    "震惊", "惊了", "吓尿", "看哭了", "泪目", "疯了", "疯狂",
    "千万不要", "99%的人都", "10亿人都", "重磅", "紧急",
    "彻底炸了", "全网疯传", "删前速看", "刚刚",
    "shock", "crazy", "you won't believe", "mind blown",
    "never seen", "incredible", "amazing",
]

# 标题党标点 (3+ 感叹号/问号)
_CLICKBAIT_PUNCT = re.compile(r"[!！?？]{3,}")

# 垃圾关键词
_SPAM_WORDS = [
    "免费领取", "点击领取", "转发抽奖", "点赞抽奖",
    "加微信", "加QQ", "私信我", "评论区",
    "免费教学", "日赚", "月入", "兼职",
    "致富", "暴利", "轻松赚钱",
    "free", "click here", "subscribe",
]

# 视频标题样式加分关键词
_QUALITY_SIGNALS = [
    "教程", "指南", "干货", "深度", "解析",
    "测评", "对比", "评测", "推荐", "盘点",
    "方法论", "框架", "系统", "原理",
    "tutorial", "guide", "review", "analysis",
    "how to", "why", "best", "top",
]

# 蹭热点 (纯数字+日期模式)
_TRENDING_DATE = re.compile(r"202[3-6]|20[2-3]\d年")


def apply_seo_rules(title: str) -> tuple[int, list[str]]:
    """SEO/标题分析规则

    Returns:
        (score_delta, reasons)
    """
    total = 0
    reasons: list[str] = []

    if not title or not title.strip():
        return -20, ["标题为空"]

    # 标题太短
    if _TITLE_TOO_SHORT.search(title):
        total -= 15
        reasons.append("标题过短 (< 8 字符)")

    # 标题太长 (> 80 字符)
    if len(title) > 80:
        total -= 5
        reasons.append("标题过长 (> 80 字符)")

    # 震惊体检测
    found_clickbait = [w for w in _CLICKBAIT_WORDS if w in title.lower()]
    if found_clickbait:
        total -= 10 * min(len(found_clickbait), 3)
        reasons.append(f"检测到标题党关键词: {found_clickbait[:3]}")

    # 标题党标点
    if _CLICKBAIT_PUNCT.search(title):
        total -= 5
        reasons.append("标题包含连续感叹号/问号")

    # 质量信号加分
    found_quality = [w for w in _QUALITY_SIGNALS if w in title.lower()]
    if found_quality:
        total += 8 * min(len(found_quality), 3)
        reasons.append(f"检测到高质量信号词: {found_quality[:3]}")

    # 含日期/年份 (蹭热点倾向)
    if _TRENDING_DATE.search(title):
        total += 3
        reasons.append("标题包含时效性信息")

    # 标题长度适中 (8-30 字最佳)
    if 8 <= len(title) <= 30:
        total += 5
        reasons.append("标题长度适中")

    return total, reasons


# ============================================================
# 时长规则
# ============================================================

def apply_duration_rules(
    duration_seconds: float,
    platform: str = "unknown",
) -> tuple[int, list[str]]:
    """时长分析规则

    Args:
        duration_seconds: 视频时长 (秒)
        platform: 平台名

    Returns:
        (score_delta, reasons)
    """
    total = 0
    reasons: list[str] = []

    if duration_seconds <= 0:
        return 0, []

    ideal = PLATFORM_IDEAL_DURATION.get(platform, PLATFORM_IDEAL_DURATION["unknown"])
    min_good, max_good, max_accept = ideal

    minutes = duration_seconds / 60

    if duration_seconds < 10:
        total -= 20
        reasons.append(f"视频过短 ({minutes:.1f}分钟, {platform}最佳区间 "
                        f"{min_good//60}-{max_good//60}分钟)")

    elif duration_seconds < min_good:
        total -= 5
        reasons.append(f"视频偏短 ({minutes:.1f}分钟, {platform}最佳区间 "
                        f"{min_good//60}-{max_good//60}分钟)")

    elif min_good <= duration_seconds <= max_good:
        total += 10
        reasons.append(f"视频时长符合{platform}最佳区间 "
                        f"({min_good//60}-{max_good//60}分钟)")

    elif duration_seconds <= max_accept:
        total += 0
        reasons.append(f"视频时长可接受 ({minutes:.1f}分钟)")

    else:
        total -= 10
        reasons.append(f"视频过长 ({minutes:.1f}分钟, 超过{platform}推荐上限 "
                        f"{max_good//60}分钟)")

    return total, reasons


# ============================================================
# 营销/推广规则
# ============================================================

# 营销词 (标题中的推广信号)
_MARKETING_KEYWORDS = [
    "广告", "推广", "赞助", "合作", "商务",
    "带货", "团购", "优惠", "折扣", "促销",
    "限时", "特价", "秒杀", "买它",
    "ad", "sponsored", "promotion", "collab",
]

# 低质量信号
_LOW_QUALITY_TITLE_PATTERNS = [
    r"^测试",           # 测试视频
    r"^test",            # test video
    r"^【?.{0,5}】?$",  # 纯括号标题
    r"^\d{5,}$",         # 纯数字
]


def apply_marketing_rules(title: str) -> tuple[int, list[str]]:
    """营销/广告检测规则"""
    total = 0
    reasons: list[str] = []

    if not title:
        return 0, []

    # 营销词检测
    found_marketing = [w for w in _MARKETING_KEYWORDS if w in title.lower()]
    if found_marketing:
        total -= 15
        reasons.append(f"检测到推广信号词: {found_marketing[:3]}")

    # 低质量标题模式
    for pattern in _LOW_QUALITY_TITLE_PATTERNS:
        if re.search(pattern, title):
            total -= 20
            reasons.append(f"标题疑似低质量内容 (匹配: {pattern})")
            break

    return total, reasons


# ============================================================
# 综合评分
# ============================================================

GRADE_THRESHOLDS: list[tuple[int, str, str]] = [
    (85, "S", "必须提取 — 高价值内容"),
    (70, "A", "建议提取"),
    (55, "B", "值得提取"),
    (40, "C", "低优先级"),
    (0,  "D", "跳过 — 不值得提取"),
]


def compute_grade(score: float) -> tuple[str, str]:
    """根据分数计算等级

    Returns:
        (grade, description)
    """
    for threshold, grade, desc in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade, desc
    return "D", "跳过 — 不值得提取"


def run_all_rules(
    title: str,
    duration_seconds: float,
    platform: str = "unknown",
    base_score: float = 50.0,
) -> tuple[float, str, list[str]]:
    """运行所有预筛规则

    Args:
        title: 视频标题
        duration_seconds: 视频时长 (秒)
        platform: 平台名
        base_score: 基础分 (默认 50)

    Returns:
        (final_score, grade, all_reasons)
    """
    all_reasons: list[str] = []
    score = base_score

    # SEO 规则
    seo_delta, seo_reasons = apply_seo_rules(title)
    score += seo_delta
    all_reasons.extend(seo_reasons)

    # 时长规则
    dur_delta, dur_reasons = apply_duration_rules(duration_seconds, platform)
    score += dur_delta
    all_reasons.extend(dur_reasons)

    # 营销规则
    mkt_delta, mkt_reasons = apply_marketing_rules(title)
    score += mkt_delta
    all_reasons.extend(mkt_reasons)

    # 截断 0-100
    score = max(0.0, min(100.0, score))

    grade, grade_desc = compute_grade(score)
    all_reasons.insert(0, f"评分 {score:.0f}/100 → {grade} 级 ({grade_desc})")

    return score, grade, all_reasons
