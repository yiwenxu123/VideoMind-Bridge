"""成本感知内容路由

遍历优先级列表自动选择提取器, 失败自动跳过。
优先级: 平台原生(FREE) → yt-dlp(FREE) → yt-dlp+ASR(CHEAP) → 商业API(PREMIUM)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..utils.platform_detector import detect_platform
from ..utils.url_normalize import normalize_video_url
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

    # 结果缓存 (Dict[url, ExtractResult])。
    # 2026-11-22：默认关闭。进程级缓存由 RouterRuntime 统一管理（它的键包含
    # 成本档/ASR 链/语言，且只缓存 completeness=full）。这里保留一个 URL 单键缓存
    # 会造成两层缓存语义不一致：本层曾把 completeness="meta"（只有标题）的结果
    # 也当成功缓存，从而挡住后续更高成本的尝试。Keeping one owner is simpler.
    cache: dict[str, ExtractResult] = field(default_factory=dict)
    use_cache: bool = False


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

    def close(self) -> None:
        """关闭已实例化的提取器及其 HTTP 客户端。"""
        for extractor in self._extractors.values():
            extractor.close()
        self._extractors.clear()
        self.config.cache.clear()

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

        # 2026-11-22: URL 归一化必须发生在所有提取器之前。
        # 抖音 jingxuan?modal_id=<id> 这类写法 yt-dlp 不认，会报 Unsupported URL，
        # 而该报错又被上层合并进"可能风控"，把排查引到完全错误的方向。
        original_url = url
        url = normalize_video_url(url)
        if url != original_url:
            logger.info(f"URL 归一化: {original_url} → {url}")

        # 检查缓存
        if self.config.use_cache and url in self.config.cache:
            cached = self.config.cache[url]
            if max_cost is None or _COST_TIER_PRIORITY.get(cached.cost_tier, 99) <= _COST_TIER_PRIORITY.get(max_cost, 99):
                if request_id:
                    cached.request_id = request_id
                return cached

        # 确定优先级列表
        priority = self.config.priority or _DEFAULT_PRIORITY

        failures: list[str] = []
        failures_meta: list[dict[str, Any]] = []
        # 2026-11-21: 记录每个提取器的结构化失败原因。以前全部失败时只剩下最后一个
        # 提取器的 error_code（常为 None → 被抹成 "extract_failed"），
        # 导致"网关没起"“视频不可见”“真风控”这些需要完全不同处置的原因在下游全丢失。
        attempts: list[dict[str, Any]] = []
        last_result: ExtractResult | None = None
        # 沿途最好的"部分内容"（占位但有正文）。全部链路失败时，与其只回一串报错，
        # 不如把这份正文一并交出——但 success 仍为 False，不假装成功。
        best_partial: ExtractResult | None = None

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
                    # 真成功 (非占位)。缓存条件与 RouterRuntime 对齐：只有 full 才值得缓存，
                    # meta（只有标题/文案）缓存下来会让同进程内更贵的 ASR 尝试被跳过。
                    if self.config.use_cache and result.completeness == "full":
                        self.config.cache[url] = result
                    logger.info(f"✓ 提取成功: {name}")
                    return result

                if result.is_placeholder:
                    # 占位结果: 仅元信息/说明文本, 不缓存, 继续降级
                    failure_msg = result.error or f"{name}: 仅获取到元信息，无真实内容"
                    # 只回收**真实文案**，不收合成提示语：
                    # 判据用提取器显式打的 partial_content 标记，不靠 completeness 猜。
                    if (result.metadata or {}).get("partial_content") and (
                        best_partial is None
                        or len(result.content or "")
                        > len(best_partial.content or "")
                    ):
                        best_partial = result
                    failures.append(failure_msg)
                    attempts.append({
                        "extractor": name,
                        "error_code": result.error_code,
                        "error": failure_msg,
                    })
                    logger.warning(f"✗ 提取器 {name} 返回占位结果: {failure_msg}")
                else:
                    failure_msg = f"{name}: {result.error or '未知错误'}"
                    failures.append(failure_msg)
                    attempts.append({
                        "extractor": name,
                        "error_code": result.error_code,
                        "error": failure_msg,
                    })
                    logger.warning(f"✗ 提取失败: {failure_msg}")

            except Exception as e:
                failure_msg = f"{name}: 异常 {e}"
                failures.append(failure_msg)
                attempts.append({
                    "extractor": name,
                    "error_code": "extractor_exception",
                    "error": failure_msg,
                })
                logger.error(f"✗ 提取器 {name} 异常: {e}")

        # 所有提取器均失败
        if last_result:
            # 返回最后一个失败结果, 但包含所有失败原因; 补充沿途最佳元信息
            best_meta = _best_metadata(failures_meta)
            detected = detect_platform(url)
            if best_meta.get("title") and not last_result.title:
                last_result.title = best_meta.get("title", "")
            # 失败结果的 platform 必须是"链接所属平台"，而不是最后那个提取器名。
            # 例：抖音链接全部失败时，last_result 来自 ytdlp_asr，其 platform 字段是
            # "ytdlp_asr"，会让按平台聚合的指标/看板把抖音故障记到一个不存在的平台上。
            # 提取器身份由 source 与 attempts 表达，platform 只表示内容来源。
            if detected != "unknown":
                last_result.platform = detected
            elif best_meta.get("platform") and last_result.platform == "unknown":
                last_result.platform = best_meta.get("platform", "")
            if best_meta.get("duration_seconds"):
                last_result.duration_seconds = best_meta.get("duration_seconds", 0.0)
            last_result.success = False
            last_result.error = "; ".join(failures)
            # 错误码优先级：平台原生提取器（如 douyin）> 任意有原因的提取器 > 兜底。
            # 这样上层拿到的 error_code 说的是"抖音网关不可达"，而不是无信息量的 extract_failed。
            native_code = next(
                (
                    a["error_code"]
                    for a in attempts
                    if a["extractor"] == detected and a["error_code"]
                ),
                None,
            )
            any_code = next((a["error_code"] for a in attempts if a["error_code"]), None)
            last_result.error_code = (
                native_code or any_code or last_result.error_code or "extract_failed"
            )
            # 全部链路失败，但沿途拿到过**真实文案**（如抖音网关给了 desc 却没播放地址）：
            # 直接把那份结果交出去，而不是回一个只有报错的对象。
            # success 保持 True 是刻意的——下游以 success!==true 为致命错误，
            # 完整性由 completeness="meta" 表达（下游有自己的密度校验）。
            if best_partial is not None and len(best_partial.content or "") > len(
                last_result.content or ""
            ):
                partial = best_partial
                # 路由在这里决定"这份部分内容值得交出去"，因此显式置 success=True：
                # 不依赖提取器传进来的值（不同提取器可能标 False），也不让下游
                # 因为 success=false 而把这唯一可用内容当硬错误丢掉。
                partial.success = True
                partial.is_placeholder = True
                if not partial.title and last_result.title:
                    partial.title = last_result.title
                if not partial.duration_seconds:
                    partial.duration_seconds = last_result.duration_seconds
                partial.error = "; ".join(failures)
                partial.metadata = {
                    **(partial.metadata or {}),
                    "attempts": attempts,
                    "partial": True,
                }
                partial.request_id = request_id or partial.request_id
                logger.warning("△ 仅取得部分内容 (%s)，已按 meta 返回", partial.source)
                return partial
            last_result.metadata = {
                **(last_result.metadata or {}),
                "attempts": attempts,
                "partial_from": best_partial.source if best_partial else None,
            }
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
