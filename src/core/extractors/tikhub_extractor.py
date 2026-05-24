"""Tikhub.io 商业 API 提取器

提供 1000+ API 覆盖 16+ 平台 (抖音/B站/小红书/Instagram/Twitter 等)。
需要 TIKHUB_API_KEY 环境变量或配置文件中的 api_key。

成本: ~$0.001/请求
"""

from __future__ import annotations

import re
from typing import Optional

import httpx

from ..models import CostTier, ExtractResult
from .base import ContentExtractor
from . import register_extractor

TIKHUB_API_BASE = "https://api.tikhub.io"

# tikhub 支持提取的平台范围
_SUPPORTED_PLATFORMS = {
    "douyin": re.compile(r"douyin\.com|iesdouyin\.com"),
    "bilibili": re.compile(r"bilibili\.com|b23\.tv"),
    "xiaohongshu": re.compile(r"xiaohongshu\.com|xhslink\.com"),
    "tiktok": re.compile(r"tiktok\.com"),
    "instagram": re.compile(r"instagram\.com"),
    "twitter": re.compile(r"twitter\.com|x\.com"),
    "youtube": re.compile(r"youtube\.com|youtu\.be"),
    "weibo": re.compile(r"weibo\.com"),
}


def _detect_commercial_platform(url: str) -> Optional[str]:
    for platform, pattern in _SUPPORTED_PLATFORMS.items():
        if pattern.search(url):
            return platform
    return None


class TikhubExtractor(ContentExtractor):
    """Tikhub.io 商业 API 提取器"""

    platform_name = "tikhub"
    _cost_tier = CostTier.PREMIUM
    url_pattern = re.compile(r"|".join(p.pattern for p in _SUPPORTED_PLATFORMS.values()))

    def __init__(self) -> None:
        self._api_key: Optional[str] = None
        self._client = httpx.Client(
            timeout=60.0,
            headers={"User-Agent": "VideoMind-Bridge/1.0"},
        )

    def is_available(self) -> bool:
        key = self._resolve_api_key("tikhub")
        self._api_key = key.strip() if key and key.strip() else None
        return self._api_key is not None

    def supports(self, url: str) -> bool:
        return bool(self.url_pattern.search(url))

    def extract(self, url: str) -> ExtractResult:
        platform = _detect_commercial_platform(url)
        if not platform:
            return ExtractResult(
                success=False, platform="unknown", title="", content="",
                source="tikhub", url=url, cost_tier=self._cost_tier,
                error="tikhub 不支持此 URL",
            )

        if not self._api_key:
            return ExtractResult(
                success=False, platform=platform, title="", content="",
                source="tikhub", url=url, cost_tier=self._cost_tier,
                error="TIKHUB_API_KEY 未配置",
            )

        try:
            result_json = self._call_api(url, platform)
            return self._parse_response(result_json, url, platform)
        except Exception as e:
            return ExtractResult(
                success=False, platform=platform, title="", content="",
                source="tikhub", url=url, cost_tier=self._cost_tier,
                error=f"Tikhub API 调用失败: {e}",
            )

    def _call_api(self, url: str, platform: str) -> dict:
        headers = {
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if platform in ("douyin", "tiktok"):
            endpoint = f"{TIKHUB_API_BASE}/api/v1/{platform}/video_info"
        elif platform == "bilibili":
            endpoint = f"{TIKHUB_API_BASE}/api/v1/bilibili/video_info"
        elif platform == "xiaohongshu":
            endpoint = f"{TIKHUB_API_BASE}/api/v1/xiaohongshu/note_info"
        elif platform == "instagram":
            endpoint = f"{TIKHUB_API_BASE}/api/v1/instagram/post_info"
        elif platform == "twitter":
            endpoint = f"{TIKHUB_API_BASE}/api/v1/twitter/tweet_info"
        elif platform == "youtube":
            endpoint = f"{TIKHUB_API_BASE}/api/v1/youtube/video_info"
        elif platform == "weibo":
            endpoint = f"{TIKHUB_API_BASE}/api/v1/weibo/post_info"
        else:
            endpoint = f"{TIKHUB_API_BASE}/api/v1/content/extract"

        resp = self._client.post(
            endpoint,
            json={"url": url},
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

    def _parse_response(self, data: dict, url: str, platform: str) -> ExtractResult:
        """解析 Tikhub API 响应为 ExtractResult"""
        title = data.get("data", {}).get("title", "") or data.get("title", "")
        content_parts = []
        desc = data.get("data", {}).get("description", "") or data.get("description", "")
        if desc:
            content_parts.append(desc)
        text = data.get("data", {}).get("text", "") or data.get("text", "")
        if text:
            content_parts.append(text)
        transcript = data.get("data", {}).get("transcript", "") or data.get("transcript", "")
        if transcript:
            content_parts.append(transcript)
        duration = data.get("data", {}).get("duration", 0) or data.get("duration", 0)
        duration_sec = float(duration) if duration else 0.0

        return ExtractResult(
            success=True,
            platform=platform,
            title=title or "未获取到标题",
            content="\n\n".join(content_parts) if content_parts else "tikhub 返回了空内容",
            source="tikhub",
            url=url,
            cost_tier=self._cost_tier,
            duration_seconds=duration_sec,
            language=data.get("data", {}).get("language", None),
            metadata={
                "api_provider": "tikhub.io",
                "raw_response_keys": list(data.keys()),
            },
        )


register_extractor("tikhub", TikhubExtractor)
