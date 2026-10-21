"""小红书 (Xiaohongshu) 内容提取器

通过页面解析提取笔记内容 (标题/正文),
零 Cookie (仅依赖页面 HTML 数据)。
参考: keepongo/video_subtitle.py 的 _parse_xhs_page()。
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

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
from ..platforms.http import platform_get
from ..platforms.rate_limit import (
    PlatformRateLimiter,
    PlatformRequestError,
    get_platform_rate_limiter,
)
from ..platforms.session import get_session_manager
from . import register_extractor
from ._ssr import find_ssr_payload
from .base import ContentExtractor

logger = logging.getLogger(__name__)

# 小红书 URL 模式 (xhslink.cn 为 2025 启用的新短链域名, 兼容 .com)
_XHS_RE = re.compile(r"(?:xiaohongshu\.com/(?:explore|discovery/item)/|xhslink\.(?:com|cn)/)(\w+)")
_XHS_SHORT_RE = re.compile(r"xhslink\.(?:com|cn)/(\w+)")
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)


class XiaohongshuExtractor(ContentExtractor):
    """小红书内容提取器"""

    platform_name = "xiaohongshu"
    _cost_tier = CostTier.FREE
    url_pattern = re.compile(r"(xiaohongshu\.com|xhslink\.(?:com|cn))")

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        limiter: PlatformRateLimiter | None = None,
    ) -> None:
        # 手机 UA: 小红书桌面 UA 的 SSR 不返回笔记内容, 仅移动端页面含 noteData
        headers = {"User-Agent": MOBILE_UA}
        session = get_session_manager().get("xiaohongshu")
        if session is not None:
            headers.update(session.headers())

        self._limiter = limiter or get_platform_rate_limiter()
        self._client = client or httpx.Client(
            timeout=30.0,
            headers=headers,
            follow_redirects=True,
        )

    def is_available(self) -> bool:
        """无需 Cookie, 始终可用"""
        return True

    def extract(self, url: str, options: ExtractOptions | None = None) -> ExtractResult:
        try:
            # 解析短链接 (xhslink.com / xhslink.cn)
            if "xhslink." in url:
                resolved = self._resolve_short_url(url)
                if resolved:
                    url = str(resolved)

            note_id = self._extract_note_id(url)
            if not note_id:
                return ExtractResult(
                    success=False, platform="xiaohongshu", title="", content="",
                    source="xiaohongshu", url=url, cost_tier=CostTier.FREE,
                    error=f"无法解析小红书笔记 ID: {url}",
                )

            # 获取笔记内容
            title, content, images, is_video, html = self._fetch_note(note_id, url)

            # 视频笔记优先口播 ASR（成功=full；失败落回 desc/meta）
            if is_video:
                video_result = self._try_video_asr(
                    html, url, note_id, title, content, options
                )
                if video_result is not None:
                    return video_result

            if not content and not title:
                return ExtractResult(
                    success=False, platform="xiaohongshu", title="", content="",
                    source="xiaohongshu", url=url, cost_tier=CostTier.FREE,
                    error="无法获取小红书笔记内容 (可能需要 Cookie)",
                )

            full_content = title
            if content:
                full_content += f"\n\n{content}" if full_content else content

            return ExtractResult(
                success=True,
                platform="xiaohongshu",
                title=title or f"小红书笔记 {note_id}",
                content=full_content,
                source="xiaohongshu",
                url=url,
                cost_tier=CostTier.FREE,
                language="zh",
                is_placeholder=not bool(content),
                metadata={
                    "note_id": note_id,
                    "images": images,
                },
                completeness="meta" if is_video else "full",
                method="desc" if is_video else "page",
            )

        except Exception as e:
            return ExtractResult(
                success=False, platform="xiaohongshu", title="", content="",
                source="xiaohongshu", url=url, cost_tier=CostTier.FREE,
                error=f"小红书提取失败: {e}",
            )

    def _extract_note_id(self, url: str) -> str | None:
        """从 URL 提取笔记 ID"""
        m = _XHS_RE.search(url)
        if m:
            return m.group(1)
        return None

    def _fetch_note(
        self, note_id: str, original_url: str = ""
    ) -> tuple[str, str, list[str], bool, str]:
        """获取笔记内容

        保留原始 URL 中的 xsec_token/xsec_source 参数（未登录访问必需），
        其余追踪参数丢弃。
        """
        note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
        if original_url:
            xsec_params = [
                f"{k}={v}" for _, k, v in re.findall(
                    r"([?&])(xsec_token|xsec_source)=([^&]+)", original_url
                )
            ]
            if xsec_params:
                note_url += "?" + "&".join(xsec_params)

        try:
            resp = platform_get(
                self.platform_name,
                self._client,
                note_url,
                timeout=15.0,
                limiter=self._limiter,
            )
            html = resp.text

            title = self._extract_title(html)
            content = self._extract_content(html)
            images = self._extract_images(html)

            # 页面提取不完整时, 尝试 SSR 数据补充
            if not content or not title:
                ssr_title, ssr_content = self._extract_from_ssr(html)
                if ssr_content:
                    content = ssr_content
                if ssr_title and not title:
                    title = ssr_title

            return title, content, images, self._is_video_html(html), html

        except (httpx.HTTPError, PlatformRequestError):
            return "", "", [], False, ""

    @staticmethod
    def _find_note_payload(data: dict) -> dict:
        """兼容新版 note.noteDetailMap 与旧版 noteData.data.noteData。"""
        if not isinstance(data, dict):
            return {}
        container = data.get("note")
        if isinstance(container, dict):
            detail_map = container.get("noteDetailMap")
            if isinstance(detail_map, dict):
                for entry in detail_map.values():
                    if not isinstance(entry, dict):
                        continue
                    candidate = entry.get("note")
                    if isinstance(candidate, dict):
                        return candidate
            if container.get("video") or container.get("desc") or container.get("title"):
                return container
        for key in ("noteDetail", "currentNote"):
            candidate = data.get(key)
            if isinstance(candidate, dict):
                return candidate
        nd = data.get("noteData", {}).get("data", {})
        if isinstance(nd, dict):
            for entry in nd.values():
                if isinstance(entry, dict):
                    candidate = entry.get("note") or entry
                    if isinstance(candidate, dict):
                        return candidate
        return {}

    @staticmethod
    def _extract_video_urls(note: dict) -> list[str]:
        stream = ((note.get("video") or {}).get("media") or {}).get("stream") or {}
        items = stream.get("h264") or stream.get("h265") or []
        if not isinstance(items, list):
            return []
        items = [item for item in items if isinstance(item, dict)]
        if not items:
            return []
        best = max(
            items,
            key=lambda item: int(
                item.get("videoBitrate") or item.get("video_bitrate") or 0
            ),
        )
        candidates = [
            best.get("masterUrl"),
            best.get("master_url"),
            *(best.get("backupUrls") or []),
            *(best.get("backup_urls") or []),
        ]
        seen: set[str] = set()
        urls: list[str] = []
        for candidate in candidates:
            if isinstance(candidate, str) and candidate and candidate not in seen:
                seen.add(candidate)
                urls.append(candidate)
        return urls

    def _try_video_asr(
        self, html: str, url: str, note_id: str, title: str,
        desc: str, options: ExtractOptions | None = None,
    ) -> ExtractResult | None:
        data = find_ssr_payload(html)
        if data is None:
            return None
        note = self._find_note_payload(data)
        video_urls = self._extract_video_urls(note)
        if not video_urls:
            logger.warning("[XiaohongshuExtractor] 视频笔记无 h264/h265 直链，落回 desc")
            return None

        duration_ms = (note.get("video") or {}).get("duration") or 0
        author = (note.get("user") or {}).get("nickname", "")
        for video_url in video_urls:
            try:
                with tempfile.TemporaryDirectory(prefix="vmb_xhs_") as tmp:
                    dest = Path(tmp) / "video.mp4"
                    HttpMediaFetcher().fetch(
                        MediaFetchRequest(
                            url=video_url,
                            dest=dest,
                            headers={
                                "User-Agent": MOBILE_UA,
                                "Referer": "https://www.xiaohongshu.com/",
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
                logger.warning(f"[XiaohongshuExtractor] 视频候选失败: {exc}")
                continue
            except Exception as exc:
                logger.warning(f"[XiaohongshuExtractor] 视频链路异常: {exc}")
                continue

            logger.info(f"[XiaohongshuExtractor] 口播 ASR 完成 {len(transcript.text)} 字符")
            return transcript_to_extract_result(
                transcript,
                url=url,
                platform="xiaohongshu",
                title=title or (note.get("title") or "小红书视频"),
                source="xiaohongshu_asr",
                cost_tier=CostTier.FREE,
                duration_seconds=float(duration_ms) / 1000 if duration_ms else 0.0,
                metadata={
                    "note_id": note_id,
                    "author": author,
                    "description": desc[:200],
                },
            )
        return None

    @staticmethod
    def _is_video_html(html: str) -> bool:
        """判断笔记是否为视频：视频页只有发布文案，没有口播全文。"""
        return bool(re.search(r'"type"\s*:\s*"video"|"noteType"\s*:\s*1', html))

    @staticmethod
    def _extract_title(html: str) -> str:
        """提取标题"""
        patterns = [
            r'<meta\s+property="og:title"\s+content="([^"]*)"',
            r'<title>([^<]*)</title>',
            r'"title"\s*:\s*"([^"]+)"',
        ]
        for p in patterns:
            m = re.search(p, html)
            if m:
                title = m.group(1).strip()
                if title and "小红书" not in title:
                    return title
        return ""

    @staticmethod
    def _extract_content(html: str) -> str:
        """提取正文内容"""
        patterns = [
            r'<meta\s+property="og:description"\s+content="([^"]*)"',
            r'"desc"\s*:\s*"([^"]+)"',
            r'"description"\s*:\s*"([^"]+)"',
            r'"content"\s*:\s*"([^"]+)"',
        ]
        for p in patterns:
            m = re.search(p, html)
            if m:
                text = m.group(1).strip()
                if len(text) > 10:
                    return text
        return ""

    @staticmethod
    def _extract_images(html: str) -> list[str]:
        """提取图片列表"""
        images = []
        patterns = [
            r'"image_list"\s*:\s*\[(.*?)\]',
            r'"imageList"\s*:\s*\[(.*?)\]',
            r'"images"\s*:\s*\[(.*?)\]',
        ]
        for p in patterns:
            m = re.search(p, html, re.DOTALL)
            if m:
                urls = re.findall(r'"([^"]*\.(?:jpg|png|webp)[^"]*)"', m.group(1))
                images.extend(urls[:9])  # 最多 9 张图
        return images

    @staticmethod
    def _extract_from_ssr(html: str) -> tuple[str, str]:
        """从 SSR 数据提取"""
        data = find_ssr_payload(html)
        if data is None:
            return "", ""
        try:
            note = XiaohongshuExtractor._find_note_payload(data)
            if not note:
                return "", ""
            title = note.get("title", "") or note.get("displayTitle", "") or ""
            desc = note.get("desc", "") or note.get("description", "") or ""

            # 拼接正文
            text_list = note.get("textList", []) or note.get("contentList", []) or []
            if text_list:
                desc = "\n".join(
                    t.get("text", "") if isinstance(t, dict) else str(t)
                    for t in text_list
                )

            return title, desc
        except (AttributeError):
            return "", ""


register_extractor("xiaohongshu", XiaohongshuExtractor)
