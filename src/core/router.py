"""成本感知内容路由

遍历优先级列表自动选择提取器, 失败自动跳过。
优先级: coze(CHEAP) → 平台原生(FREE) → yt-dlp(FREE) → yt-dlp+ASR(CHEAP) → 商业API(PREMIUM)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .extractors import create_all_extractors
from .extractors.base import ContentExtractor
from .models import _COST_TIER_PRIORITY, CostTier, ExtractResult

logger = logging.getLogger(__name__)


@dataclass
class RouterConfig:
    """路由配置"""

    # 最大可接受成本等级 (None = 不限制)
    max_cost_tier: CostTier | None = None

    # 自定义提取器优先级列表 (名称列表)
    priority: list[str] | None = None

    # 结果缓存 (Dict[url, ExtractResult])
    cache: dict[str, ExtractResult] = field(default_factory=dict)


# 默认提取器优先级 (按提取能力排列)
# Coze 优先 — 使用免费每日积分，覆盖全平台提取+转写
# Coze 失败后按平台走各自的免费链路，最后用付费 API 兜底
_DEFAULT_PRIORITY = [
    "coze",        # CHEAP   - 免费每日积分，全平台通用
    "bilibili",    # FREE    - B站字幕API，Coze 失败时兜底
    "youtube",     # FREE    - YouTube字幕API
    "douyin",      # FREE    - 抖音页面解析
    "xiaohongshu", # FREE    - 小红书页面解析
    "ytdlp",       # FREE    - yt-dlp 字幕兜底
    "ytdlp_asr",   # CHEAP   - yt-dlp下载+阿里云ASR (无字幕视频转写)
    "tikhub",      # PREMIUM - TikHub商业API (付费兜底)
    "apify",       # PREMIUM - Apify商业爬虫
]


class ContentRouter:
    """内容路由: 按优先级遍历提取器, 自动降级"""

    def __init__(self, config: RouterConfig | None = None) -> None:
        self.config = config or RouterConfig()
        self._extractors: dict[str, ContentExtractor] = {}
        self._init_extractors()

    def _init_extractors(self) -> None:
        """初始化所有提取器"""
        for extractor in create_all_extractors():
            self._extractors[extractor.platform_name] = extractor

    def get_extractor(self, name: str) -> ContentExtractor | None:
        """获取指定名称的提取器"""
        return self._extractors.get(name)

    def list_extractors(self) -> dict[str, bool]:
        """列出所有提取器及其可用状态"""
        result: dict[str, bool] = {}
        for name, ext in self._extractors.items():
            result[name] = ext.is_available()
        return result

    def extract(self, url: str, max_cost: CostTier | None = None) -> ExtractResult:
        """提取内容, 自动遍历优先级列表

        Args:
            url: 视频/内容 URL
            max_cost: 最大可接受成本 (None = 不限制)

        Returns:
            ExtractResult: 第一个成功的提取结果, 或全部失败的汇总
        """
        # 检查缓存
        if url in self.config.cache:
            cached = self.config.cache[url]
            if max_cost is None or _COST_TIER_PRIORITY.get(cached.cost_tier, 99) <= _COST_TIER_PRIORITY.get(max_cost, 99):
                return cached

        # 确定优先级列表
        priority = self.config.priority or _DEFAULT_PRIORITY

        failures: list[str] = []
        last_result: ExtractResult | None = None

        for name in priority:
            extractor = self._extractors.get(name)
            if extractor is None:
                continue

            if not extractor.supports(url):
                continue

            if not extractor.is_available():
                logger.debug(f"提取器 {name} 不可用 (跳过)")
                continue

            effective_max = max_cost or self.config.max_cost_tier
            if (
                effective_max is not None
                and _COST_TIER_PRIORITY.get(extractor.cost_tier(), 99) > _COST_TIER_PRIORITY.get(effective_max, 99)
            ):
                logger.debug(f"提取器 {name} 成本超限 (跳过)")
                continue

            try:
                logger.info(f"尝试提取器: {name}")
                result = extractor.extract(url)
                last_result = result

                if result.success and result.content.strip() and not result.is_placeholder:
                    # 真成功 (非占位): 缓存并返回
                    self.config.cache[url] = result
                    logger.info(f"✓ 提取成功: {name}")
                    return result

                if result.is_placeholder:
                    # 占位结果: 仅元信息/说明文本, 不缓存, 继续降级
                    failure_msg = result.error or f"{name}: 仅获取到元信息，无真实内容"
                    failures.append(failure_msg)
                    logger.warning(f"✗ 提取器 {name} 返回占位结果: {failure_msg}")
                else:
                    failure_msg = f"{name}: {result.error or '未知错误'}"
                    failures.append(failure_msg)
                    logger.warning(f"✗ 提取失败: {failure_msg}")

            except Exception as e:
                failure_msg = f"{name}: 异常 {e}"
                failures.append(failure_msg)
                logger.error(f"✗ 提取器 {name} 异常: {e}")

        # 所有提取器均失败
        if last_result:
            # 返回最后一个失败结果, 但包含所有失败原因
            last_result.success = False
            last_result.error = "; ".join(failures)
            return last_result

        return ExtractResult(
            success=False,
            platform="unknown",
            title="",
            content="",
            source="router",
            url=url,
            cost_tier=CostTier.FREE,
            error=f"无可用提取器: {'; '.join(failures) if failures else '所有提取器均不支持此 URL'}",
        )
