"""成本感知内容路由

遍历优先级列表自动选择提取器, 失败自动跳过。
优先级: 平台原生(FREE) → yt-dlp(FREE) → yt-dlp+ASR(CHEAP) → 商业API(PREMIUM)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .extractors import list_extractor_classes
from .extractors.base import ContentExtractor
from .models import _COST_TIER_PRIORITY, CostTier, ExtractOptions, ExtractResult


def _best_metadata(meta_list: list[dict[str, Any]]) -> dict[str, Any]:
    """从失败尝试的元信息中挑选最完整的一条（有标题优先，其次时长/平台）。"""
    best: dict[str, Any] = {}
    for meta in meta_list:
        if not meta.get("title"):
            continue
        if not best or len(best.get("title", "")) < len(meta.get("title", "")):
            best = meta
    return best

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
    "bilibili",    # FREE    - B站字幕API (官方 WBI 签名)
    "youtube",     # FREE    - YouTube字幕API
    "douyin",      # FREE    - 抖音页面解析
    "xiaohongshu", # FREE    - 小红书页面解析
    "ytdlp",       # FREE    - yt-dlp 字幕兜底
    "ytdlp_asr",   # CHEAP   - yt-dlp下载+DashScope ASR (无字幕视频转写)
    "tikhub",      # PREMIUM - TikHub商业API (付费兜底)
    "apify",       # PREMIUM - Apify商业爬虫
]


class ContentRouter:
    """内容路由: 按优先级遍历提取器, 自动降级"""

    def __init__(self, config: RouterConfig | None = None) -> None:
        self.config = config or RouterConfig()
        self._extractor_classes = list_extractor_classes()
        self._extractors: dict[str, ContentExtractor] = {}

    def _get_extractor(self, name: str) -> ContentExtractor | None:
        """按需实例化并缓存提取器；未注册返回 None。"""
        cls = self._extractor_classes.get(name)
        if cls is None:
            return None
        if name not in self._extractors:
            self._extractors[name] = cls()
        return self._extractors[name]

    def get_extractor(self, name: str) -> ContentExtractor | None:
        """获取指定名称的提取器"""
        return self._get_extractor(name)

    def list_extractors(self) -> dict[str, bool]:
        """列出所有提取器及其可用状态（会实例化全部，仅用于能力探测）"""
        result: dict[str, bool] = {}
        for name in self._extractor_classes:
            extractor = self._get_extractor(name)
            if extractor is not None:
                result[name] = extractor.is_available()
        return result

    def extract(
        self,
        url: str,
        max_cost: CostTier | None = None,
        options: ExtractOptions | None = None,
    ) -> ExtractResult:
        """提取内容, 自动遍历优先级列表

        Args:
            url: 视频/内容 URL
            max_cost: 最大可接受成本 (None = 不限制)
            options: 请求级选项（ASR 链/语言/请求 ID）

        Returns:
            ExtractResult: 第一个成功的提取结果, 或全部失败的汇总
        """
        request_id = options.request_id if options else None

        # 检查缓存
        if url in self.config.cache:
            cached = self.config.cache[url]
            if max_cost is None or _COST_TIER_PRIORITY.get(cached.cost_tier, 99) <= _COST_TIER_PRIORITY.get(max_cost, 99):
                if request_id:
                    cached.request_id = request_id
                return cached

        # 确定优先级列表
        priority = self.config.priority or _DEFAULT_PRIORITY

        failures: list[str] = []
        failures_meta: list[dict[str, Any]] = []
        last_result: ExtractResult | None = None

        for name in priority:
            extractor = self._get_extractor(name)
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
                if options is not None:
                    # 位置参数：各提取器第二参数可能叫 options 或 _options
                    result = extractor.extract(url, options)
                else:
                    result = extractor.extract(url)
                last_result = result
                if request_id and not result.request_id:
                    result.request_id = request_id
                if result.title:
                    failures_meta.append({
                        "platform": result.platform,
                        "title": result.title,
                        "duration_seconds": result.duration_seconds,
                    })

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
            # 返回最后一个失败结果, 但包含所有失败原因; 补充沿途最佳元信息
            best_meta = _best_metadata(failures_meta)
            if best_meta.get("title") and not last_result.title:
                last_result.title = best_meta.get("title", "")
            if best_meta.get("platform") and last_result.platform == "unknown":
                last_result.platform = best_meta.get("platform", "")
            if best_meta.get("duration_seconds"):
                last_result.duration_seconds = best_meta.get("duration_seconds", 0.0)
            last_result.success = False
            last_result.error = "; ".join(failures)
            last_result.error_code = last_result.error_code or "extract_failed"
            last_result.request_id = request_id or last_result.request_id
            return last_result

        # 全部失败且无结果对象时, 保留沿途拿到的最佳元信息 (标题/时长)
        best_meta = _best_metadata(failures_meta)
        return ExtractResult(
            success=False,
            platform=best_meta.get("platform", "unknown"),
            title=best_meta.get("title", ""),
            content="",
            source="router",
            url=url,
            cost_tier=CostTier.FREE,
            duration_seconds=best_meta.get("duration_seconds", 0.0),
            metadata={"attempted": failures},
            error=f"无可用提取器: {'; '.join(failures) if failures else '所有提取器均不支持此 URL'}",
            error_code="unsupported_url",
            request_id=request_id,
        )
