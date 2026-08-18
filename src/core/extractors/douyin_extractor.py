"""抖音 (Douyin) 内容提取器

使用 iesdouyin 移动端 API 提取字幕/文案。
本地/云 IP 易被验证码风控, 可通过 DOUYIN_COOKIES_FILE 指定 cookies.txt (Netscape 格式) 绕过。
参考: keepongo/video_subtitle.py 的 _douyin_share_api() 实现。
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from ..models import CostTier, ExtractResult
from . import register_extractor
from ._ssr import find_first_meta, find_ssr_payload
from .base import ContentExtractor

# 抖音 URL 模式
_DOUYIN_RE = re.compile(
    r"(?:douyin\.com/(?:video|share)/|douyin\.com/jingxuan\?modal_id=|iesdouyin\.com/share/video/|v\.douyin\.com/)(\w+)"
)
_DOUYIN_SHORT_RE = re.compile(r"v\.douyin\.com/(\w+)")


def _load_cookies_file(path: str) -> str:
    """读取 Netscape cookies.txt, 拼装为 Cookie header。

    文件格式 (yt-dlp/浏览器导出):
        domain \t includeSubdomains \t path \t secure \t expiry \t name \t value
    """
    try:
        with open(path, encoding="utf-8") as f:
            parts = []
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                fields = line.split("\t")
                if len(fields) >= 7:
                    parts.append(f"{fields[5]}={fields[6]}")
            return "; ".join(parts)
    except (OSError, IndexError):
        return ""


class DouyinExtractor(ContentExtractor):
    """抖音内容提取器"""

    platform_name = "douyin"
    _cost_tier = CostTier.FREE
    url_pattern = re.compile(r"(douyin\.com|iesdouyin\.com)")

    def __init__(self) -> None:
        # 手机 UA 更易通过风控; 可通过 DOUYIN_COOKIES_FILE 提供 cookies.txt 绕过验证码
        cookies_file = os.getenv("DOUYIN_COOKIES_FILE", "")
        cookie_header = _load_cookies_file(cookies_file) if cookies_file else ""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/16.0 Mobile/15E148 Safari/604.1"
            ),
        }
        if cookie_header:
            headers["Cookie"] = cookie_header

        self._client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers=headers,
        )
        self._has_cookies = bool(cookie_header)

    def is_available(self) -> bool:
        """无 Cookie 也可用 (部分 IP 可直抓)"""
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
                    is_placeholder=True,
                    metadata={"video_id": video_id},
                    error=(
                        "无可用字幕 (页面可能被验证码风控; "
                        "可配置 DOUYIN_COOKIES_FILE 或由 yt-dlp ASR 兜底)"
                    ),
                )

            # 文案过短 (< 120 字, 抖音 desc 通常=标题): 视为无实质内容,
            # 返回占位触发降级, 由 yt-dlp+本地 whisper 转写真实讲话内容
            if len(content) < 120:
                return ExtractResult(
                    success=False,
                    platform="douyin",
                    title=title or f"抖音视频 {video_id}",
                    content=f"[抖音] {title or video_id}\n文案过短 (对话在画面中), 已降级 ASR 转写。",
                    source="douyin",
                    url=url,
                    cost_tier=CostTier.FREE,
                    is_placeholder=True,
                    metadata={"video_id": video_id, "desc_short": True},
                    error="抖音文案过短 (desc≈标题), 触发 yt-dlp+ASR 降级",
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
                # 尝试从 SSR 数据提取
                description = self._extract_from_ssr(html)

            # 页面文案提取失败 (验证码壳页等) 时, 主动走 detail API
            if not description:
                api_title, api_desc, _ = self._fetch_via_share_api(video_id)
                if api_desc:
                    return api_title or title, api_desc, None

            return title, description, None

        except httpx.HTTPError:
            # HTTP 错误时尝试备用 API
            return self._fetch_via_share_api(video_id)

    def _fetch_via_share_api(
        self, video_id: str,
    ) -> tuple[str, str, list[dict[str, Any]] | None]:
        """通过抖音 Web detail API 二次尝试

        使用 www.douyin.com 域名 + Cookie (ttwid/__ac_signature 匿名风控签名),
        iesdouyin 域名在云 IP 下返回 403。
        """
        try:
            api_url = (
                "https://www.douyin.com/aweme/v1/web/aweme/detail/"
                f"?aweme_id={video_id}&device_platform=webapp&aid=6383"
            )
            resp = self._client.get(api_url, timeout=10.0,
                headers={
                    "Accept": "application/json",
                    "Referer": "https://www.douyin.com/",
                })
            resp.raise_for_status()
            data = resp.json()
            aweme = data.get("aweme_detail", {})
            if not isinstance(aweme, dict):
                return "", "", None
            desc = aweme.get("desc", "") or ""
            title = desc or aweme.get("share_info", {}).get("share_title", "")
            return title, desc, None
        except Exception:
            return "", "", None

    @staticmethod
    def _extract_title(html: str) -> str:
        """从 HTML 提取标题"""
        return find_first_meta(html, [
            r'<meta\s+property="og:title"\s+content="([^"]*)"',
            r'<title>([^<]*)</title>',
            r'"desc"\s*:\s*"([^"]*)"',
        ])

    @staticmethod
    def _extract_description(html: str) -> str:
        """从 HTML 提取描述/文案"""
        return find_first_meta(html, [
            r'<meta\s+property="og:description"\s+content="([^"]*)"',
            r'"description"\s*:\s*"([^"]*)"',
        ])

    @staticmethod
    def _extract_from_ssr(html: str) -> str:
        """从 SSR 数据提取文案"""
        data = find_ssr_payload(html)
        if data is None:
            return ""
        try:
            # 不同结构遍历
            desc = data.get("videoInfoRes", {}).get("item_list", [{}])[0].get("desc", "")
            if desc:
                return str(desc)
            desc = data.get("aweme_detail", {}).get("desc", "")
            if desc:
                return str(desc)
        except (IndexError, KeyError):
            return ""
        return ""


register_extractor("douyin", DouyinExtractor)
