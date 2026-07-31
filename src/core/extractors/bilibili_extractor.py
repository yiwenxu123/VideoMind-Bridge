"""Bilibili 内容提取器

使用 WBI 签名 + Bilibili 官方字幕 API, 零 Cookie 直接提取。
参考: keepongo/video-subtitle 的 WBI 签名实现。
"""

from __future__ import annotations

import hashlib
import re
import time
import urllib.parse
from typing import Any

import httpx

from ..models import CostTier, ExtractResult
from . import register_extractor
from .base import ContentExtractor

# Bilibili WBI 签名常量和密钥池
MIXIN_KEY_ENC_TABLE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 37, 12, 52, 56, 7,
    0, 16, 22, 38, 59, 55, 11, 61, 34, 40, 26, 17, 51, 41, 60, 39,
    20, 13, 48, 6, 36, 24, 44, 25, 21, 4, 54, 57, 30, 1,
]

# 默认 WBI 密钥 (当 API 获取失败时使用)
_FALLBACK_WBI_KEY = "ea1db124afe2e5b2"

_BV_RE = re.compile(r"/(BV\w+)")
_EP_RE = re.compile(r"/(EP\w+)")
_SS_RE = re.compile(r"/(SS\w+)")
_B23_RE = re.compile(r"b23\.tv/(\w+)")


class BilibiliExtractor(ContentExtractor):
    """Bilibili 内容提取器"""

    platform_name = "bilibili"
    _cost_tier = CostTier.FREE
    url_pattern = re.compile(r"(bilibili\.com|b23\.tv)")

    def __init__(self) -> None:
        self._wbi_key: str | None = None
        self._client = httpx.Client(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com",
            },
        )

    def is_available(self) -> bool:
        """Bilibili 提取器始终可用 (无需 Cookie/Token)"""
        return True

    def extract(self, url: str) -> ExtractResult:
        try:
            bvid = self._resolve_video_id(url)
            if not bvid:
                return ExtractResult(
                    success=False, platform="bilibili", title="", content="",
                    source="bilibili", url=url, cost_tier=CostTier.FREE,
                    error=f"无法从 URL 解析视频 ID: {url}",
                )

            # 1. 获取视频信息 (标题、时长等)
            info = self._get_video_info(bvid)
            title = info.get("title", "")
            duration = info.get("duration", 0)

            # 2. 获取字幕
            subtitle_content, segments, language = self._get_subtitle(bvid)

            if not subtitle_content:
                return ExtractResult(
                    success=False,
                    platform="bilibili",
                    title=title,
                    content=f"[Bilibili 视频] {title}\n时长: {duration}秒\n"
                            f"无可用字幕。请使用 yt-dlp 或 Whisper 提取音频转录。",
                    source="bilibili",
                    url=url,
                    cost_tier=CostTier.FREE,
                    duration_seconds=float(duration),
                    language="zh",
                    metadata={"bvid": bvid, "video_info": info},
                )

            return ExtractResult(
                success=True,
                platform="bilibili",
                title=title,
                content=subtitle_content,
                source="bilibili",
                url=url,
                cost_tier=CostTier.FREE,
                duration_seconds=float(duration),
                language=language or "zh",
                segments=segments,
                metadata={"bvid": bvid, "video_info": info},
            )

        except httpx.HTTPStatusError as e:
            return ExtractResult(
                success=False, platform="bilibili", title="", content="",
                source="bilibili", url=url, cost_tier=CostTier.FREE,
                error=f"Bilibili API 错误: HTTP {e.response.status_code}",
            )
        except Exception as e:
            return ExtractResult(
                success=False, platform="bilibili", title="", content="",
                source="bilibili", url=url, cost_tier=CostTier.FREE,
                error=f"Bilibili 提取失败: {e}",
            )

    def _get_wbi_key(self) -> str:
        """获取 WBI 签名密钥"""
        if self._wbi_key is not None:
            return self._wbi_key

        try:
            resp = self._client.get("https://api.bilibili.com/x/web-interface/nav")
            data = resp.json()
            if data.get("code") == 0 and data.get("data", {}).get("isLogin") is not None:
                img_url: str = data["data"]["wbi_img"]["img_url"]
                sub_url: str = data["data"]["wbi_img"]["sub_url"]
                img_key = img_url.rsplit("/", 1)[1].split(".")[0]
                sub_key = sub_url.rsplit("/", 1)[1].split(".")[0]
                self._wbi_key = self._mixin_key(img_key + sub_key)
            else:
                self._wbi_key = _FALLBACK_WBI_KEY
        except Exception:
            self._wbi_key = _FALLBACK_WBI_KEY

        return self._wbi_key

    @staticmethod
    def _mixin_key(orig: str) -> str:
        """WBI mixin key 计算"""
        return "".join(orig[i] for i in MIXIN_KEY_ENC_TABLE if i < len(orig))[:32]

    @staticmethod
    def _wbi_sign(params: dict[str, str], wbi_key: str) -> dict[str, str]:
        """对参数字典进行 WBI 签名"""
        params["wts"] = str(int(time.time()))
        sorted_params = sorted(params.items())
        query = urllib.parse.urlencode(sorted_params)
        sign_str = query + wbi_key
        params["w_rid"] = hashlib.md5(sign_str.encode()).hexdigest()
        return params

    def _resolve_video_id(self, url: str) -> str | None:
        """解析视频 ID (支持 BV/EP/SS/短链接)"""
        # 短链接
        if "b23.tv" in url:
            m = _B23_RE.search(url)
            if m:
                resolved = self._resolve_b23_url(url)
                if resolved:
                    return self._resolve_video_id(resolved)
            return None

        # BV / EP / SS
        for pattern in [_BV_RE, _EP_RE, _SS_RE]:
            m = pattern.search(url)
            if m:
                return m.group(1)
        return None

    def _resolve_b23_url(self, url: str) -> str | None:
        """解析 b23.tv 短链接"""
        try:
            resp = self._client.get(url, follow_redirects=True)
            return str(resp.url)
        except Exception:
            return None

    def _get_video_info(self, bvid: str) -> dict[str, Any]:
        """获取视频元信息"""
        params = {"bvid": bvid}
        signed = self._wbi_sign(params, self._get_wbi_key())
        resp = self._client.get(
            "https://api.bilibili.com/x/web-interface/view",
            params=signed,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Bilibili API 返回错误: {data.get('message', 'unknown')}")

        vdata = data["data"]
        return {
            "title": vdata.get("title", ""),
            "duration": vdata.get("duration", 0),
            "author": vdata.get("owner", {}).get("name", ""),
            "description": vdata.get("desc", ""),
            "aid": vdata.get("aid"),
        }

    def _get_subtitle(self, bvid: str) -> tuple[str, list, str | None]:
        """获取字幕内容"""
        params = {"bvid": bvid}
        signed = self._wbi_sign(params, self._get_wbi_key())
        resp = self._client.get(
            "https://api.bilibili.com/x/web-interface/view",
            params=signed,
        )
        data = resp.json()

        if data.get("code") != 0:
            return "", [], None

        player_info = data.get("data", {})
        subtitle_list = player_info.get("subtitle", {}).get("subtitles", [])

        if not subtitle_list:
            return "", [], None

        # 优先选择中文字幕
        subtitle_url = None
        lang = None
        for sub in subtitle_list:
            if sub.get("lan_doc", "").lower() in ("中文", "chinese", "zh-cn", "zh"):
                subtitle_url = sub.get("subtitle_url", "")
                lang = sub.get("lan", "zh")
                break

        if not subtitle_url:
            subtitle_url = subtitle_list[0].get("subtitle_url", "")
            lang = subtitle_list[0].get("lan", "zh")

        if not subtitle_url:
            return "", [], None

        # 完整的字幕 JSON URL
        if subtitle_url.startswith("//") or subtitle_url.startswith("/"):
            subtitle_url = "https:" + subtitle_url

        sub_resp = self._client.get(subtitle_url)
        sub_data = sub_resp.json()

        # 提取字幕文本和片段
        text_parts: list[str] = []
        segments: list[dict[str, Any]] = []
        for item in sub_data.get("body", []):
            text = item.get("content", "")
            if text:
                text_parts.append(text)
                segments.append({
                    "start": item.get("from", 0),
                    "end": item.get("to", 0),
                    "text": text,
                })

        return "\n".join(text_parts), segments, lang


register_extractor("bilibili", BilibiliExtractor)
