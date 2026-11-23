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

# 2026-11-23：熔断作用域。与抖音一致，把"页面直抓"与平台其它链路隔离，
# 避免本提取器的失败连带熔断同平台下本来可用的兜底（yt-dlp / 本地 ASR）。
_CIRCUIT_SCOPE = "xiaohongshu:crawl"
# 2026-11-22：失败原因 → (error_code, 给用户的处置建议)。
# 措辞原则：陈述事实 + 给出下一步动作，**不做猜测**。
# 旧文案"可能需要 Cookie"是猜测，会把人引向"上浏览器/配 Cookie"这种又贵又不解决根因的操作。
_NOTE_FAILURE_HINTS: dict[str, tuple[str, str]] = {
    "token_invalid": (
        "xhs_token_invalid",
        "链接里的分享参数(xsec_token)已失效或被判无效；"
        "请在小红书 App 内重新「分享 → 复制链接」后重试",
    ),
    "note_unavailable": (
        "xhs_note_unavailable",
        "笔记当前不可见（已删除 / 设为私密 / 分享链接过期）；"
        "请确认笔记状态，或重新分享获取新链接",
    ),
    "login_required": (
        "xhs_login_required",
        "小红书要求登录态；配置 VMB_XHS_COOKIE 或 VMB_XHS_COOKIES_FILE 后重试",
    ),
    "risk_control": (
        "xhs_risk_control",
        "触发小红书风控；稍后重试，或配置登录态提高通过率",
    ),
    "http_error": (
        "xhs_http_error",
        "请求小红书失败（网络或服务端异常）；稍后重试",
    ),
    "no_content": (
        "xhs_no_content",
        "已取到笔记页面但没有正文；该笔记可能是纯图片、无文字说明",
    ),
}

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
            title, content, images, is_video, html, failure = self._fetch_note(note_id, url)

            # 视频笔记优先口播 ASR（成功=full；失败落回 desc/meta）
            if is_video:
                video_result = self._try_video_asr(
                    html, url, note_id, title, content, options
                )
                if video_result is not None:
                    return video_result

            if not content and not title:
                # 归因：不同原因处置完全不同（重分享 / 换链接 / 配登录态 / 等一会），
                # 不能都报成"可能需要 Cookie"。
                code, hint = _NOTE_FAILURE_HINTS.get(
                    failure or "note_unavailable",
                    ("xhs_extract_failed", "未能获取小红书笔记内容"),
                )
                logger.info(
                    "[XiaohongshuExtractor] 取数失败 note_id=%s failure=%s",
                    note_id,
                    failure,
                )
                return ExtractResult(
                    success=False, platform="xiaohongshu", title="", content="",
                    source="xiaohongshu", url=url, cost_tier=CostTier.FREE,
                    error=hint,
                    error_code=code,
                    metadata={"note_id": note_id, "failure": failure},
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
                    "note_type": "video" if is_video else "image",
                    "failure": failure,
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
    ) -> tuple[str, str, list[str], bool, str, str | None]:
        """获取笔记内容

        保留原始 URL 中的 xsec_token/xsec_source 参数（未登录访问必需），
        其余追踪参数丢弃。

        Returns:
            (title, content, images, is_video, html, failure)
            failure 取值见 ``_NOTE_FAILURE_HINTS``；成功时为 None。

        2026-11-22：此前异常被吞成空元组，上层只能报"可能需要 Cookie"——那是猜测。
        实测一条真实图文笔记会返回 **HTTP 200 的空壳页**（``noteData`` 只剩
        ``routeQuery``、整页无 ``noteId``），与"被风控""需要登录"是完全不同的处置。
        现在把原因显式带出去。
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
                circuit_key=_CIRCUIT_SCOPE,
            )
            html = resp.text
            final_path = resp.url.path or ""

            # 软 404：小红书把"token 缺失/错误/私密/删除/限流"统一导向
            # /404/sec_xxx（source=xhs_sec_server），页面本身不告知原因。
            if "/404/" in final_path:
                return "", "", [], False, html, "token_invalid"

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

            failure: str | None = None
            if not title and not content:
                # 200 但笔记数据缺失：noteData 里没有 noteId 就说明这一页根本没渲染笔记。
                # 常见于 token 失效后的降级空壳，或笔记已删除/转私密。
                failure = (
                    "note_unavailable"
                    if "noteId" not in html
                    else "no_content"
                )

            return (
                title,
                content,
                images,
                self._is_video_html(html),
                html,
                failure,
            )

        except PlatformRequestError as exc:
            if exc.code == "auth_required":
                return "", "", [], False, "", "login_required"
            if exc.code == "risk_control":
                return "", "", [], False, "", "risk_control"
            return "", "", [], False, "", "http_error"
        except httpx.HTTPError:
            return "", "", [], False, "", "http_error"

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
        # 2026-11-23：门槛按字段区分。
        # 原来统一 `len(text) > 10`，会把"3 个技巧"这类短文案静默丢掉；
        # 但最后一条 "content" 是泛化字段，容易抓到无关小串，保留较高门槛。
        patterns: list[tuple[str, int]] = [
            (r'<meta\s+property="og:description"\s+content="([^"]*)"', 1),
            (r'"desc"\s*:\s*"([^"]+)"', 1),
            (r'"description"\s*:\s*"([^"]+)"', 1),
            (r'"content"\s*:\s*"([^"]+)"', 10),
        ]
        for pattern, min_len in patterns:
            m = re.search(pattern, html)
            if m:
                text = m.group(1).strip()
                if len(text) >= min_len:
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
