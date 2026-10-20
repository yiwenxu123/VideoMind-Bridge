"""抖音 (Douyin) 内容提取器

使用 iesdouyin 移动端 API 提取字幕/文案。
本地/云 IP 易被验证码风控, 可通过 DOUYIN_COOKIES_FILE 指定 cookies.txt (Netscape 格式) 绕过。
参考: keepongo/video_subtitle.py 的 _douyin_share_api() 实现。
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import httpx

from ..asr import (
    AsrChainError,
    MediaRef,
    TranscribeOptions,
    transcribe_with_chain,
    transcript_to_extract_result,
)
from ..media import HttpMediaFetcher, MediaFetchError, MediaFetchRequest
from ..models import CostTier, ExtractOptions, ExtractResult
from . import register_extractor
from ._ssr import find_first_meta, find_ssr_payload
from .base import ContentExtractor

logger = logging.getLogger(__name__)

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

    def extract(self, url: str, options: ExtractOptions | None = None) -> ExtractResult:
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

            # 优先走 douyin-api 网关 + 音频 ASR（与内容运营agent 本地链路对齐）
            gateway_result = self._extract_via_gateway(video_id, url, options)
            if gateway_result is not None:
                return gateway_result

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
                    completeness="none",
                    method="desc",
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
                    completeness="meta",
                    method="desc",
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
                completeness="meta",
                method="desc",
            )

        except Exception as e:
            return ExtractResult(
                success=False, platform="douyin", title="", content="",
                source="douyin", url=url, cost_tier=CostTier.FREE,
                error=f"抖音提取失败: {e}",
            )

    def _extract_via_gateway(
        self, video_id: str, url: str, options: ExtractOptions | None = None,
    ) -> ExtractResult | None:
        """douyin-api 网关 + 视频下载 + ASR（失败返回 None 由页面/文案路径兜底）。"""
        api_base = os.getenv("DOUYIN_API_URL", "http://127.0.0.1:8010").rstrip("/")
        try:
            resp = self._client.get(
                f"{api_base}/api/douyin/web/fetch_one_video",
                params={"aweme_id": video_id},
                timeout=30.0,
            )
            body = resp.json()
        except Exception as exc:
            logger.warning(f"[DouyinExtractor] 网关不可用，回退页面解析: {exc}")
            return None

        detail = (body.get("data") or {}).get("aweme_detail")
        if body.get("code") != 200 or not isinstance(detail, dict):
            logger.warning(
                f"[DouyinExtractor] 网关 code={body.get('code')} 无详情，回退页面解析"
            )
            return None

        desc = str(detail.get("desc") or "").strip()
        title = str(detail.get("title") or desc or f"抖音视频 {video_id}").strip()
        author = (detail.get("author") or {}).get("nickname", "")
        duration_ms = detail.get("duration") or (detail.get("video") or {}).get("duration") or 0
        duration = float(duration_ms) / 1000 if duration_ms else 0.0

        video = detail.get("video") or {}
        play_urls = (video.get("play_addr") or {}).get("url_list") or []
        video_url = next(
            (u for u in play_urls if isinstance(u, str) and u.startswith("http")), None
        )
        if not video_url:
            return self._gateway_meta_result(
                video_id, url, title, desc, author, duration, source="douyin_gateway"
            )

        try:
            with tempfile.TemporaryDirectory(prefix="vmb_douyin_") as tmp:
                dest = Path(tmp) / "video.mp4"
                HttpMediaFetcher().fetch(
                    MediaFetchRequest(
                        url=video_url,
                        dest=dest,
                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/130.0.0.0 Safari/537.36"
                            ),
                            "Referer": "https://www.douyin.com/",
                        },
                        timeout=120.0,
                        max_bytes=300 * 1024 * 1024,
                    )
                )
                transcript = transcribe_with_chain(
                    MediaRef(path=dest),
                    TranscribeOptions(
                        language=options.asr_language if options else None,
                        max_cost=options.asr_max_cost if options else None,
                    ),
                    chain=options.asr_chain if options else None,
                    default_language="zh",
                )
        except (MediaFetchError, AsrChainError) as exc:
            logger.warning(f"[DouyinExtractor] 网关音频链路失败，降级 meta: {exc}")
            return self._gateway_meta_result(
                video_id, url, title, desc, author, duration, source="douyin_gateway"
            )
        except Exception as exc:
            logger.warning(f"[DouyinExtractor] 网关提取异常，降级 meta: {exc}")
            return self._gateway_meta_result(
                video_id, url, title, desc, author, duration, source="douyin_gateway"
            )

        logger.info(f"[DouyinExtractor] 网关 ASR 完成 {len(transcript.text)} 字符")
        return transcript_to_extract_result(
            transcript,
            url=url,
            platform="douyin",
            title=title,
            source="douyin_asr",
            cost_tier=CostTier.FREE,
            duration_seconds=duration,
            metadata={
                "aweme_id": video_id,
                "author": author,
                "description": desc[:200],
            },
        )

    def _gateway_meta_result(
        self, video_id: str, url: str, title: str, desc: str,
        author: str, duration: float, source: str,
    ) -> ExtractResult | None:
        if len(desc) < 30:
            return None
        return ExtractResult(
            success=True,
            platform="douyin",
            title=title or f"抖音视频 {video_id}",
            content=desc,
            source=source,
            url=url,
            cost_tier=CostTier.FREE,
            duration_seconds=duration,
            language="zh",
            metadata={
                "aweme_id": video_id,
                "author": author,
                "description": desc[:200],
            },
            completeness="meta",
            method="desc",
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
