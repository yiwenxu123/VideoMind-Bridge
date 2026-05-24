"""Apify 商业 API 提取器

使用 Apify 预构建爬虫抓取 B站/抖音等平台的字幕和元信息。
需要 APIFY_API_KEY 环境变量:
  - APIFY_API_KEY: Apify API Token

成本: ~$4.99/1000 次 (按平台爬虫不同)
"""

from __future__ import annotations

import re

import httpx

from ..models import CostTier, ExtractResult
from . import register_extractor
from .base import ContentExtractor

APIFY_API_BASE = "https://api.apify.com/v2"

# Apify 爬虫 Actor ID 映射
_ACTOR_MAP: dict[str, str] = {
    "bilibili": "srcful/bilibili-video-scraper",
    "douyin": "drobnikj/douyin-video-scraper",
    "youtube": "bernardo/youtube-scraper",
    "xiaohongshu": "awescode/xiaohongshu-scraper",
    "tiktok": "drobnikj/tiktok-scraper",
}

_SUPPORTED_PATTERNS = {
    "bilibili": re.compile(r"bilibili\.com|b23\.tv"),
    "douyin": re.compile(r"douyin\.com|iesdouyin\.com"),
    "youtube": re.compile(r"youtube\.com|youtu\.be"),
    "xiaohongshu": re.compile(r"xiaohongshu\.com|xhslink\.com"),
    "tiktok": re.compile(r"tiktok\.com"),
}


def _detect_apify_platform(url: str) -> str | None:
    for platform, pattern in _SUPPORTED_PATTERNS.items():
        if pattern.search(url):
            return platform
    return None


class ApifyExtractor(ContentExtractor):
    """Apify 商业爬虫提取器"""

    platform_name = "apify"
    _cost_tier = CostTier.PREMIUM
    url_pattern = re.compile(r"|".join(p.pattern for p in _SUPPORTED_PATTERNS.values()))

    def __init__(self) -> None:
        self._api_key: str | None = None
        self._client = httpx.Client(timeout=120.0)

    def is_available(self) -> bool:
        key = self._resolve_api_key("apify")
        self._api_key = key.strip() if key and key.strip() else None
        return self._api_key is not None

    def supports(self, url: str) -> bool:
        return bool(self.url_pattern.search(url))

    def extract(self, url: str) -> ExtractResult:
        platform = _detect_apify_platform(url)
        if not platform:
            return ExtractResult(
                success=False, platform="unknown", title="", content="",
                source="apify", url=url, cost_tier=self._cost_tier,
                error="Apify 不支持此 URL",
            )

        if not self._api_key:
            return ExtractResult(
                success=False, platform=platform, title="", content="",
                source="apify", url=url, cost_tier=self._cost_tier,
                error="APIFY_API_KEY 未配置",
            )

        actor_id = _ACTOR_MAP.get(platform)
        if not actor_id:
            return ExtractResult(
                success=False, platform=platform, title="", content="",
                source="apify", url=url, cost_tier=self._cost_tier,
                error=f"Apify 无可用爬虫: {platform}",
            )

        try:
            result_data = self._run_actor(actor_id, url)
            return self._parse_result(result_data, url, platform)
        except Exception as e:
            return ExtractResult(
                success=False, platform=platform, title="", content="",
                source="apify", url=url, cost_tier=self._cost_tier,
                error=f"Apify API 调用失败: {e}",
            )

    def _run_actor(self, actor_id: str, url: str) -> list[dict]:
        """调用 Apify Actor 并返回结果"""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        run_resp = self._client.post(
            f"{APIFY_API_BASE}/acts/{actor_id}/runs",
            headers=headers,
            json={"input": {"url": url}},
            params={"waitForFinish": 120},
        )
        run_resp.raise_for_status()
        run_data = run_resp.json()
        run_id = run_data.get("data", {}).get("id")

        if not run_id:
            raise RuntimeError(f"Apify Actor 启动失败: {run_data}")

        dataset_resp = self._client.get(
            f"{APIFY_API_BASE}/actor-runs/{run_id}/dataset/items",
            headers=headers,
        )
        dataset_resp.raise_for_status()
        return dataset_resp.json()

    def _parse_result(self, data: list[dict], url: str, platform: str) -> ExtractResult:
        """解析 Apify 爬虫结果为 ExtractResult"""
        if not data:
            return ExtractResult(
                success=False, platform=platform, title="", content="",
                source="apify", url=url, cost_tier=self._cost_tier,
                error="Apify 返回了空结果",
            )

        item = data[0] if isinstance(data, list) else data
        title = item.get("title") or item.get("fullTitle") or item.get("name", "")
        desc = item.get("description") or item.get("text", "")

        text_parts = [desc] if desc else []
        transcript = item.get("transcript") or item.get("subtitles", "")
        if transcript:
            if isinstance(transcript, list):
                transcript = " ".join(s.get("text", "") for s in transcript)
            text_parts.append(transcript)
        duration = item.get("duration") or item.get("length", 0)

        return ExtractResult(
            success=True,
            platform=platform,
            title=title or "未获取到标题",
            content="\n\n".join(text_parts) if text_parts else "Apify 返回了空内容",
            source="apify",
            url=url,
            cost_tier=self._cost_tier,
            duration_seconds=float(duration) if duration else 0.0,
            language=item.get("language", None),
            metadata={
                "api_provider": "apify",
                "actor_id": _ACTOR_MAP.get(platform),
            },
        )


register_extractor("apify", ApifyExtractor)
