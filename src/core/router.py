"""成本感知内容路由

遍历优先级列表自动选择提取器, 失败自动跳过。
优先级: 直接API(FREE) → Coze(CHEAP) → yt-dlp(FREE) → Whisper(EXPENSIVE) → 商业API(PREMIUM)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .extractors import create_all_extractors
from .extractors.base import ContentExtractor
from .models import CostTier, ExtractResult

logger = logging.getLogger(__name__)


@dataclass
class RouterConfig:
    """路由配置"""

    # 最大可接受成本等级 (None = 不限制)
    max_cost_tier: Optional[CostTier] = None

    # 是否启用所有提取器
    all_extractors: bool = False

    # 自定义提取器优先级列表 (名称列表)
    priority: Optional[List[str]] = None

    # 尝试的超时时间 (秒)
    timeout: int = 300

    # 结果缓存 (Dict[url, ExtractResult])
    cache: Dict[str, ExtractResult] = field(default_factory=dict)


# 默认提取器优先级 (按成本/id 排序)
_DEFAULT_PRIORITY = [
    "bilibili",    # FREE - 直接API, 零Cookie
    "youtube",     # FREE - 直接API
    "douyin",      # FREE - iesdouyin
    "xiaohongshu", # FREE - 页面解析
    "coze",        # CHEAP - Coze API (有Token时)
    "ytdlp",       # FREE - yt-dlp 兜底字幕
]


class ContentRouter:
    """内容路由: 按优先级遍历提取器, 自动降级"""

    def __init__(self, config: Optional[RouterConfig] = None) -> None:
        self.config = config or RouterConfig()
        self._extractors: Dict[str, ContentExtractor] = {}
        self._init_extractors()

    def _init_extractors(self) -> None:
        """初始化所有提取器"""
        for extractor in create_all_extractors():
            self._extractors[extractor.platform_name] = extractor

    def get_extractor(self, name: str) -> Optional[ContentExtractor]:
        """获取指定名称的提取器"""
        return self._extractors.get(name)

    def list_extractors(self) -> Dict[str, bool]:
        """列出所有提取器及其可用状态"""
        result: Dict[str, bool] = {}
        for name, ext in self._extractors.items():
            result[name] = ext.is_available()
        return result

    def extract(self, url: str, max_cost: Optional[CostTier] = None) -> ExtractResult:
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
            if max_cost is None or cached.cost_tier.value <= max_cost.value:
                return cached

        # 确定优先级列表
        priority = self.config.priority or _DEFAULT_PRIORITY

        failures: List[str] = []
        last_result: Optional[ExtractResult] = None

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
            if effective_max is not None:
                cost_order = {
                    CostTier.FREE: 0, CostTier.CHEAP: 1,
                    CostTier.PAID: 2, CostTier.EXPENSIVE: 3,
                    CostTier.PREMIUM: 4,
                }
                if cost_order.get(extractor.cost_tier(), 99) > cost_order.get(effective_max, 99):
                    logger.debug(f"提取器 {name} 成本超限 (跳过)")
                    continue

            try:
                logger.info(f"尝试提取器: {name}")
                result = extractor.extract(url)
                last_result = result

                if result.success:
                    # 缓存成功结果
                    self.config.cache[url] = result
                    logger.info(f"✓ 提取成功: {name}")
                    return result
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
