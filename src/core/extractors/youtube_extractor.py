"""YouTube 内容提取器

使用 youtube-transcript-api 直接提取字幕, 零 Cookie。
降级: oembed 元信息 → yt-dlp 字幕。
"""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

import httpx

from ..models import CostTier, ExtractResult
from . import register_extractor
from .base import ContentExtractor

# YouTube 视频 ID 模式
_VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([\w-]{11})"
)
_YT_DOMAIN_RE = re.compile(r"(youtube\.com|youtu\.be)")


class YouTubeExtractor(ContentExtractor):
    """YouTube 内容提取器"""

    platform_name = "youtube"
    _cost_tier = CostTier.FREE
    url_pattern = re.compile(r"(youtube\.com|youtu\.be)")

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=30.0)

    def is_available(self) -> bool:
        return True

    def extract(self, url: str) -> ExtractResult:
        try:
            video_id = self._extract_video_id(url)
            if not video_id:
                return ExtractResult(
                    success=False, platform="youtube", title="", content="",
                    source="youtube", url=url, cost_tier=CostTier.FREE,
                    error=f"无法从 URL 解析视频 ID: {url}",
                )

            # 1. 尝试通过 oembed 获取标题
            title = self._get_title(video_id)

            # 2. 获取字幕
            subtitle_text, segments, language = self._get_transcript(video_id)

            if not subtitle_text:
                return ExtractResult(
                    success=True,
                    platform="youtube",
                    title=title or f"YouTube 视频 {video_id}",
                    content="",
                    source="youtube",
                    url=url,
                    cost_tier=CostTier.FREE,
                    is_placeholder=True,
                    metadata={"video_id": video_id},
                    error="无可用字幕，需要 yt-dlp 或 Whisper 转录兜底",
                )

            return ExtractResult(
                success=True,
                platform="youtube",
                title=title or f"YouTube 视频 {video_id}",
                content=subtitle_text,
                source="youtube",
                url=url,
                cost_tier=CostTier.FREE,
                language=language or "en",
                segments=segments,
                metadata={"video_id": video_id},
            )

        except Exception as e:
            return ExtractResult(
                success=False, platform="youtube", title="", content="",
                source="youtube", url=url, cost_tier=CostTier.FREE,
                error=f"YouTube 提取失败: {e}",
            )

    def _extract_video_id(self, url: str) -> str | None:
        """从 URL 提取视频 ID"""
        m = _VIDEO_ID_RE.search(url)
        if m:
            return m.group(1)

        # 尝试不带协议的裸 ID
        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme:
            # 可能是裸 ID
            if re.match(r"^[\w-]{11}$", url):
                return url

        return None

    def _get_title(self, video_id: str) -> str:
        """通过 oembed 获取视频标题"""
        try:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            resp = self._client.get(oembed_url, timeout=10.0)
            data = resp.json()
            return data.get("title", "")
        except Exception:
            return ""

    def _get_transcript(self, video_id: str) -> tuple[str, list[dict[str, Any]], str | None]:
        """通过 youtube-transcript-api 获取字幕

        直接调用 youtube-transcript-api 的内置 API 端点。
        """
        try:
            # YouTube Transcript API 端点
            url = f"https://youtubetranscript.com/?v={video_id}&format=json"
            resp = self._client.get(url, timeout=15.0)

            if resp.status_code != 200:
                # 尝试第二种方法: 通过字幕 API
                return self._get_transcript_via_youtube_api(video_id)

            data = resp.json()
            segments: list[dict[str, Any]] = []
            text_parts: list[str] = []

            for item in data:
                text = item.get("text", "")
                if text:
                    text_parts.append(text)
                    segments.append({
                        "start": item.get("start", 0),
                        "end": item.get("start", 0) + item.get("duration", 0),
                        "text": text,
                    })

            return "\n".join(text_parts), segments, "en"

        except Exception:
            return self._get_transcript_via_youtube_api(video_id)

    def _get_transcript_via_youtube_api(
        self, video_id: str,
    ) -> tuple[str, list[dict[str, Any]], str | None]:
        """通过 YouTube 内部字幕 API 获取"""
        try:
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            resp = self._client.get(watch_url, timeout=15.0,
                headers={"User-Agent": "Mozilla/5.0"})

            # 从页面提取字幕轨道 URL
            html = resp.text

            # 查找字幕轨道 URL
            pattern = r'"captionTracks"\s*:\s*(\[.*?\])'
            match = re.search(pattern, html, re.DOTALL)
            if not match:
                return "", [], None

            tracks = json.loads(match.group(1))
            if not tracks:
                return "", [], None

            # 优先中文字幕
            track_url = None
            lang = None
            for t in tracks:
                lang_code = t.get("languageCode", "")
                if lang_code in ("zh-Hans", "zh", "zh-CN", "zh-TW"):
                    track_url = t.get("baseUrl", "")
                    lang = lang_code
                    break

            if not track_url:
                track_url = tracks[0].get("baseUrl", "")
                lang = tracks[0].get("languageCode", "en")

            if not track_url:
                return "", [], None

            # 获取字幕 XML
            sub_resp = self._client.get(track_url, timeout=10.0)
            sub_text = sub_resp.text

            # 解析字幕 XML
            import xml.etree.ElementTree as ET
            root = ET.fromstring(sub_text)

            # YouTube 字幕 XML 命名空间
            ns = {"": "http://www.w3.org/ns/ttml"}

            text_parts: list[str] = []
            segments: list[dict[str, Any]] = []

            for p_elem in root.findall(".//p", ns):
                text = "".join(p_elem.itertext()).strip()
                if not text:
                    continue

                start = float(p_elem.get("begin", "0").replace("s", ""))
                dur = float(p_elem.get("dur", "0").replace("s", ""))
                text_parts.append(text)
                segments.append({
                    "start": start,
                    "end": start + dur,
                    "text": text,
                })

            return "\n".join(text_parts), segments, lang

        except Exception:
            return "", [], None


register_extractor("youtube", YouTubeExtractor)
