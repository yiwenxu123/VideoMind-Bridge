"""抖音 (Douyin) 内容提取器

使用 iesdouyin 移动端 API, 零 Cookie 提取字幕/文案。
参考: keepongo/video_subtitle.py 的 _douyin_share_api() 实现。
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..models import CostTier, ExtractResult
from . import register_extractor
from .base import ContentExtractor

# 抖音 URL 模式
_DOUYIN_RE = re.compile(
    r"(?:douyin\.com/(?:video|share)/|douyin\.com/jingxuan\?modal_id=|iesdouyin\.com/share/video/|v\.douyin\.com/)(\w+)"
)
_DOUYIN_SHORT_RE = re.compile(r"v\.douyin\.com/(\w+)")


class DouyinExtractor(ContentExtractor):
    """抖音内容提取器"""

    platform_name = "douyin"
    _cost_tier = CostTier.FREE
    url_pattern = re.compile(r"(douyin\.com|iesdouyin\.com)")

    def __init__(self) -> None:
        self._client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
        )

    def is_available(self) -> bool:
        """无需 Cookie, 始终可用"""
        return True

    def extract(self, url: str) -> ExtractResult:
        try:
            # 解析短链接
            if "v.douyin.com" in url:
                resolved = self._resolve_short_url(url)
                if resolved:
                    url = resolved

            video_id = self._extract_video_id(url)
            if not video_id:
                return ExtractResult(
                    success=False, platform="douyin", title="", content="",
                    source="douyin", url=url, cost_tier=CostTier.FREE,
                    error="暂不支持此抖音链接格式，请使用 /video/ 类链接或短链",
                )

            # 1. 获取视频信息和字幕
            title, content, segments = self._fetch_video_data(video_id)

            if not content:
                return ExtractResult(
                    success=False,
                    platform="douyin",
                    title=title or f"抖音视频 {video_id}",
                    content=f"[抖音] {title or video_id}\n无可用字幕文案。",
                    source="douyin",
                    url=url,
                    cost_tier=CostTier.FREE,
                    metadata={"video_id": video_id},
                )

            return ExtractResult(
                success=True,
                platform="douyin",
                title=title or f"抖音视频 {video_id}",
                content=content,
                source="douyin",
                url=url,
                cost_tier=CostTier.FREE,
                language="zh",
                segments=segments if segments else None,
                metadata={"video_id": video_id},
            )

        except Exception as e:
            return ExtractResult(
                success=False, platform="douyin", title="", content="",
                source="douyin", url=url, cost_tier=CostTier.FREE,
                error=f"抖音提取失败: {e}",
            )

    def _resolve_short_url(self, url: str) -> str | None:
        """解析 v.douyin.com 短链接"""
        try:
            resp = self._client.get(url, follow_redirects=True, timeout=10.0)
            return str(resp.url)
        except Exception:
            return None

    def _extract_video_id(self, url: str) -> str | None:
        """从 URL 提取视频 ID"""
        m = _DOUYIN_RE.search(url)
        if m:
            return m.group(1)
        return None

    def _fetch_video_data(
        self, video_id: str,
    ) -> tuple[str, str, list[dict[str, Any]] | None]:
        """通过 iesdouyin 移动端 API 获取视频信息

        使用 Share API (无需 Cookie):
        https://www.iesdouyin.com/share/video/{video_id}/
        """
        try:
            # 尝试分享页面
            share_url = f"https://www.iesdouyin.com/share/video/{video_id}/"
            resp = self._client.get(share_url, timeout=15.0)

            if resp.status_code != 200:
                # 降级到 Douyin 页面
                douyin_url = f"https://www.douyin.com/video/{video_id}"
                resp = self._client.get(douyin_url, timeout=15.0)

            html = resp.text

            # 从页面提取标题和文案
            title = self._extract_title(html)

            # 提取视频文案 (通过 SSR 数据)
            description = self._extract_description(html)

            if not description:
                # 尝试从 JSON-LD / 数据脚本提取
                description = self._extract_from_ssr(html)

            return title, description, None

        except httpx.HTTPError:
            # HTTP 错误时尝试备用 API
            return self._fetch_via_share_api(video_id)

    def _fetch_via_share_api(
        self, video_id: str,
    ) -> tuple[str, str, list[dict[str, Any]] | None]:
        """通过抖音分享 API 二次尝试"""
        try:
            api_url = f"https://www.iesdouyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}"
            resp = self._client.get(api_url, timeout=10.0,
                headers={"Accept": "application/json"})
            data = resp.json()
            aweme = data.get("aweme_detail", {})
            title = aweme.get("desc", "") or aweme.get("share_info", {}).get("share_title", "")
            desc = aweme.get("desc", "")
            return title, desc, None
        except Exception:
            return "", "", None

    @staticmethod
    def _extract_title(html: str) -> str:
        """从 HTML 提取标题"""
        patterns = [
            r'<meta\s+property="og:title"\s+content="([^"]*)"',
            r'<title>([^<]*)</title>',
            r'"desc"\s*:\s*"([^"]*)"',
        ]
        for p in patterns:
            m = re.search(p, html)
            if m:
                return m.group(1).strip()
        return ""

    @staticmethod
    def _extract_description(html: str) -> str:
        """从 HTML 提取描述/文案"""
        patterns = [
            r'<meta\s+property="og:description"\s+content="([^"]*)"',
            r'"description"\s*:\s*"([^"]*)"',
        ]
        for p in patterns:
            m = re.search(p, html)
            if m:
                return m.group(1).strip()
        return ""

    @staticmethod
    def _extract_from_ssr(html: str) -> str:
        """从 SSR 数据提取文案"""
        # 查找 __INITIAL_STATE__ 或 __NEXT_DATA__
        patterns = [
            r'<script>window\.__INITIAL_STATE__\s*=\s*({.*?});</script>',
            r'<script id="__NEXT_DATA__"\s*type="application/json">({.*?})</script>',
        ]
        for p in patterns:
            m = re.search(p, html, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    # 不同结构遍历
                    if isinstance(data, dict):
                        desc = data.get("videoInfoRes", {}).get("item_list", [{}])[0].get("desc", "")
                        if desc:
                            return desc
                        desc = data.get("aweme_detail", {}).get("desc", "")
                        if desc:
                            return desc
                except (json.JSONDecodeError, IndexError, KeyError):
                    continue
        return ""


register_extractor("douyin", DouyinExtractor)
