"""小红书 (Xiaohongshu) 内容提取器

通过页面解析提取笔记内容 (标题/正文),
零 Cookie (仅依赖页面 HTML 数据)。
参考: keepongo/video_subtitle.py 的 _parse_xhs_page()。
"""

from __future__ import annotations

import re

import httpx

from ..models import CostTier, ExtractResult
from . import register_extractor
from ._ssr import find_ssr_payload
from .base import ContentExtractor

# 小红书 URL 模式 (xhslink.cn 为 2025 启用的新短链域名, 兼容 .com)
_XHS_RE = re.compile(r"(?:xiaohongshu\.com/(?:explore|discovery/item)/|xhslink\.(?:com|cn)/)(\w+)")
_XHS_SHORT_RE = re.compile(r"xhslink\.(?:com|cn)/(\w+)")


class XiaohongshuExtractor(ContentExtractor):
    """小红书内容提取器"""

    platform_name = "xiaohongshu"
    _cost_tier = CostTier.FREE
    url_pattern = re.compile(r"(xiaohongshu\.com|xhslink\.(?:com|cn))")

    def __init__(self) -> None:
        # 手机 UA: 小红书桌面 UA 的 SSR 不返回笔记内容, 仅移动端页面含 noteData
        self._client = httpx.Client(
            timeout=30.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/16.0 Mobile/15E148 Safari/604.1"
                ),
            },
            follow_redirects=True,
        )

    def is_available(self) -> bool:
        """无需 Cookie, 始终可用"""
        return True

    def extract(self, url: str) -> ExtractResult:
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
            title, content, images = self._fetch_note(note_id, url)

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

    def _fetch_note(self, note_id: str, original_url: str = "") -> tuple[str, str, list[str]]:
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
            resp = self._client.get(note_url, timeout=15.0)
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
            note = (
                data.get("note", {})
                or data.get("noteDetail", {})
                or data.get("currentNote", {})
                or {}
            )
            # 新版结构: noteData.data.noteData (笔记详情在 data 首键下)
            if not note:
                nd = data.get("noteData", {}).get("data", {})
                if nd:
                    first_key = next(iter(nd))
                    first = nd[first_key]
                    if isinstance(first, dict):
                        note = first.get("note") or first
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
