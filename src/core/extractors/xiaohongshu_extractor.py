"""小红书 (Xiaohongshu) 内容提取器

通过页面解析提取笔记内容 (标题/正文),
零 Cookie (仅依赖页面 HTML 数据)。
参考: keepongo/video_subtitle.py 的 _parse_xhs_page()。
"""

from __future__ import annotations

import json
import re

import httpx

from ..models import CostTier, ExtractResult
from . import register_extractor
from .base import ContentExtractor

# 小红书 URL 模式
_XHS_RE = re.compile(r"(?:xiaohongshu\.com/(?:explore|discovery/item)/|xhslink\.com/)(\w+)")
_XHS_SHORT_RE = re.compile(r"xhslink\.com/(\w+)")


class XiaohongshuExtractor(ContentExtractor):
    """小红书内容提取器"""

    platform_name = "xiaohongshu"
    _cost_tier = CostTier.FREE
    url_pattern = re.compile(r"(xiaohongshu\.com|xhslink\.com)")

    def __init__(self) -> None:
        self._client = httpx.Client(
            timeout=30.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
            follow_redirects=True,
        )

    def is_available(self) -> bool:
        """无需 Cookie, 始终可用"""
        return True

    def extract(self, url: str) -> ExtractResult:
        try:
            # 解析短链接
            if "xhslink.com" in url:
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
            title, content, images = self._fetch_note(note_id)

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
                metadata={
                    "note_id": note_id,
                    "images": images,
                },
            )

        except Exception as e:
            return ExtractResult(
                success=False, platform="xiaohongshu", title="", content="",
                source="xiaohongshu", url=url, cost_tier=CostTier.FREE,
                error=f"小红书提取失败: {e}",
            )

    def _resolve_short_url(self, url: str) -> str | None:
        """解析 xhslink.com 短链接"""
        try:
            resp = self._client.get(url, timeout=10.0)
            # 获取最终的 URL (重定向后)
            return str(resp.url)
        except Exception:
            return None

    def _extract_note_id(self, url: str) -> str | None:
        """从 URL 提取笔记 ID"""
        m = _XHS_RE.search(url)
        if m:
            return m.group(1)
        return None

    def _fetch_note(self, note_id: str) -> tuple[str, str, list[str]]:
        """获取笔记内容"""
        note_url = f"https://www.xiaohongshu.com/explore/{note_id}"

        try:
            resp = self._client.get(note_url, timeout=15.0)
            html = resp.text

            title = self._extract_title(html)
            content = self._extract_content(html)
            images = self._extract_images(html)

            # 如果页面提取失败, 尝试 SSR 数据
            if not content and not title:
                ssr_title, ssr_content = self._extract_from_ssr(html)
                if ssr_content:
                    content = ssr_content
                if ssr_title and not title:
                    title = ssr_title

            return title, content, images

        except httpx.HTTPError:
            return "", "", []

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
        patterns = [
            r'<script>window\.__INITIAL_STATE__\s*=\s*({.*?});</script>',
            r'<script id="__NEXT_DATA__"\s*type="application/json">({.*?})</script>',
        ]
        for p in patterns:
            m = re.search(p, html, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    if isinstance(data, dict):
                        note = (
                            data.get("note", {})
                            or data.get("noteDetail", {})
                            or data.get("currentNote", {})
                            or {}
                        )
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
                except (json.JSONDecodeError, AttributeError):
                    continue
        return "", ""


register_extractor("xiaohongshu", XiaohongshuExtractor)
