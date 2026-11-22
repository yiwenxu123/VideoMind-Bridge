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
from ..platforms.http import platform_get
from ..platforms.rate_limit import (
    PlatformRateLimiter,
    PlatformRequestError,
    get_platform_rate_limiter,
)
from ..platforms.session import get_session_manager
from . import register_extractor
from ._ssr import find_first_meta, find_ssr_payload
from .base import ContentExtractor

logger = logging.getLogger(__name__)

# 抖音 URL 模式
_DOUYIN_RE = re.compile(
    r"(?:douyin\.com/(?:video|share)/|douyin\.com/jingxuan\?modal_id=|iesdouyin\.com/share/video/|v\.douyin\.com/)(\w+)"
)
_DOUYIN_SHORT_RE = re.compile(r"v\.douyin\.com/(\w+)")

# 2026-11-20 P1: 熔断作用域。
# 抖音直抓（iesdouyin 分享页 / www detail API）与 yt-dlp、本地 ASR 兜底是三条独立链路，
# 之前共用 "douyin" 一个熔断键：直抓被风控三次后，会把本来能成功的兜底一起跳掉。
# 现在直抓写 douyin:crawl，兜底各用各的键，互不牵连。
_CIRCUIT_SCOPE = "douyin:crawl"

# 2026-11-21 P0-5: 抖音会返回 **HTTP 200 的验证码壳页**——状态码正常，内容却不是目标页。
# 之前这种响应被 platform_get 记成 success，造成两个后果：
#   1. 熔断永远打不开（每次 200 把失败计数清零）；
#   2. 错误信息把"被风控"说成"无可用字幕"，把运维指向错误的处置动作。
# 判定口径：命中反爬标记 **且** 关键内容字段全部缺失。只用标记会在正常页里误伤
# （正常页的 JS bundle 里也常出现 captcha/verify 字样）。
_SHELL_MARKERS = ("verify", "captcha", "argus", "滑块", "安全验证", "secsdk")
_SHELL_CONTENT_KEYS = ('"__initial_state__"', "og:description", "aweme_detail")


def _looks_like_risk_shell(html: str) -> bool:
    """判断响应体是否为反爬壳页（有标记、无内容）。"""
    if not html:
        return False
    head = html[:30000].lower()
    if not any(marker in head for marker in _SHELL_MARKERS):
        return False
    return not any(key in head for key in _SHELL_CONTENT_KEYS)


class DouyinExtractor(ContentExtractor):
    """抖音内容提取器"""

    platform_name = "douyin"
    _cost_tier = CostTier.FREE
    url_pattern = re.compile(r"(douyin\.com|iesdouyin\.com)")

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        limiter: PlatformRateLimiter | None = None,
    ) -> None:
        # 手机 UA 更易通过风控; 登录态统一由 SessionManager 读取
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/16.0 Mobile/15E148 Safari/604.1"
            ),
        }
        session = get_session_manager().get("douyin")
        if session is not None:
            headers.update(session.headers())

        self._limiter = limiter or get_platform_rate_limiter()
        self._client = client or httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers=headers,
        )

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
            gateway_result, gateway_failure = self._extract_via_gateway(
                video_id, url, options
            )
            if gateway_result is not None:
                return gateway_result

            # 1. 获取视频信息和字幕
            title, content, segments, crawl_failure = self._fetch_video_data(video_id)

            if not content:
                # 归因（2026-11-21 P0-5）：三种失败处置完全不同，不能都报"可能被风控"。
                #   gateway_unreachable → 本机服务没起，去 pm2 restart douyin-api
                #   gateway_no_detail   → 网关通了但拿不到详情，多为视频本身不可见/受限
                #   risk_control        → 真被风控，需要登录态/cookie
                #   no_content          → 页面正常、就是没有文字，换 ASR 兜底即可
                if gateway_failure == "gateway_unreachable":
                    error_code = "douyin_gateway_unavailable"
                    error = (
                        "抖音网关不可达 (DOUYIN_API_URL="
                        f"{os.getenv('DOUYIN_API_URL', 'http://127.0.0.1:8010')})。"
                        "先修服务再重试：pm2 list | grep douyin-api；pm2 restart douyin-api"
                    )
                elif gateway_failure == "gateway_no_detail":
                    error_code = "douyin_gateway_no_detail"
                    error = (
                        "抖音网关可达但无视频详情，通常是视频不可见（审核中/仅作者可见/"
                        "已删除）或该视频被平台限制；换链接或请用户确认视频状态"
                    )
                elif crawl_failure == "risk_control":
                    error_code = "douyin_risk_control"
                    error = (
                        "抖音返回验证码壳页/风控（HTTP 200 但无内容）；"
                        "可配置 DOUYIN_COOKIES_FILE 或由 yt-dlp ASR 兜底"
                    )
                else:
                    error_code = "douyin_no_content"
                    error = "页面正常但未取到可用文案，交由 ASR 兜底"

                return ExtractResult(
                    success=False,
                    platform="douyin",
                    title=title or f"抖音视频 {video_id}",
                    content=f"[抖音] {title or video_id}\n无可用字幕文案。",
                    source="douyin",
                    url=url,
                    cost_tier=CostTier.FREE,
                    is_placeholder=True,
                    metadata={
                        "video_id": video_id,
                        "gateway_failure": gateway_failure,
                        "crawl_failure": crawl_failure,
                    },
                    error=error,
                    error_code=error_code,
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
    ) -> tuple[ExtractResult | None, str | None]:
        """douyin-api 网关 + 视频下载 + ASR。

        Returns:
            (result, failure)：成功时 failure 为 None；失败时 result 为 None 且 failure 说明原因，
            取值 gateway_unreachable / gateway_no_detail / gateway_no_content。
            区分这三者是为了让上层能给出正确的处置建议——"网关没起"该去重启服务，
            "无详情"多半是视频本身不可见，"无内容"是这条链路没取到文字。
        """
        api_base = os.getenv("DOUYIN_API_URL", "http://127.0.0.1:8010").rstrip("/")
        try:
            resp = self._client.get(
                f"{api_base}/api/douyin/web/fetch_one_video",
                params={"aweme_id": video_id},
                timeout=30.0,
            )
            body = resp.json()
        except Exception as exc:
            logger.warning(f"[DouyinExtractor] 网关不可达 {api_base}: {exc}")
            # 关键区分：网关"没起"和"平台风控"处置完全不同，不能都报成风控。
            return None, "gateway_unreachable"

        detail = (body.get("data") or {}).get("aweme_detail")
        if body.get("code") != 200 or not isinstance(detail, dict):
            filter_reason = ((body.get("data") or {}).get("filter_detail") or {}).get(
                "filter_reason"
            )
            logger.warning(
                f"[DouyinExtractor] 网关 code={body.get('code')} 无详情 "
                f"filter_reason={filter_reason or '-'}，回退页面解析"
            )
            return None, "gateway_no_detail"

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
            # 没有播放地址：退回"仅文案"结果。只有连文案都不够长（meta 返回 None）才算失败。
            meta = self._gateway_meta_result(
                video_id, url, title, desc, author, duration, source="douyin_gateway"
            )
            return meta, None if meta is not None else "gateway_no_content"

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
            meta = self._gateway_meta_result(
                video_id, url, title, desc, author, duration, source="douyin_gateway"
            )
            return meta, None if meta is not None else "gateway_no_content"
        except Exception as exc:
            logger.warning(f"[DouyinExtractor] 网关提取异常，降级 meta: {exc}")
            meta = self._gateway_meta_result(
                video_id, url, title, desc, author, duration, source="douyin_gateway"
            )
            return meta, None if meta is not None else "gateway_no_content"

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
        ), None

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
    ) -> tuple[str, str, list[dict[str, Any]] | None, str | None]:
        """通过 iesdouyin 移动端 API 获取视频信息。

        使用 Share API (无需 Cookie):
        https://www.iesdouyin.com/share/video/{video_id}/

        Returns:
            (title, content, segments, failure)
            failure: None=取到文案 / "risk_control"=验证码壳页或风控 / "no_content"=页面正常但无文案

        关键点：platform_get 的 validator 会在 200 壳页时抛 risk_control，于是本次请求
        被记成失败并计入 ``douyin:crawl`` 熔断，而不是像以前那样把壳页当成功、
        顺手把失败计数清零（这正是熔断一直打不开的原因）。
        """
        share_url = f"https://www.iesdouyin.com/share/video/{video_id}/"
        try:
            try:
                resp = platform_get(
                    self.platform_name,
                    self._client,
                    share_url,
                    timeout=15.0,
                    limiter=self._limiter,
                    circuit_key=_CIRCUIT_SCOPE,
                    validator=self._guard_shell,
                )
            except PlatformRequestError as exc:
                if exc.code in {"risk_control", "auth_required"}:
                    return "", "", None, "risk_control"
                # 分享页 404/网络异常：交给 detail API 兜底
                api_title, api_desc, api_segments = self._fetch_via_share_api(video_id)
                return api_title, api_desc, api_segments, None if api_desc else "no_content"
            except httpx.HTTPError:
                api_title, api_desc, api_segments = self._fetch_via_share_api(video_id)
                return api_title, api_desc, api_segments, None if api_desc else "no_content"

            html = resp.text

            title = self._extract_title(html)
            description = self._extract_description(html)
            if not description:
                description = self._extract_from_ssr(html)

            if not description:
                api_title, api_desc, api_segments = self._fetch_via_share_api(video_id)
                if api_desc:
                    return api_title or title, api_desc, api_segments, None
                # 页面与 detail API 都没拿到文案：区分"被壳页挡住"和"确实没有文案"
                failure = "risk_control" if _looks_like_risk_shell(html) else "no_content"
                return title, "", None, failure

            return title, description, None, None

        except (httpx.HTTPError, PlatformRequestError):
            api_title, api_desc, api_segments = self._fetch_via_share_api(video_id)
            return api_title, api_desc, api_segments, None if api_desc else "no_content"

    @staticmethod
    def _guard_shell(response: httpx.Response) -> None:
        """platform_get 的 validator：把 HTTP 200 的反爬壳页转成 risk_control 错误。"""
        if _looks_like_risk_shell(response.text):
            raise PlatformRequestError(
                "risk_control",
                "抖音返回验证码壳页 (HTTP 200 但无目标页面内容)",
                status_code=response.status_code,
                retry_after_seconds=60,
            )

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
            resp = platform_get(
                self.platform_name,
                self._client,
                api_url,
                timeout=10.0,
                headers={
                    "Accept": "application/json",
                    "Referer": "https://www.douyin.com/",
                },
                limiter=self._limiter,
                circuit_key=_CIRCUIT_SCOPE,
            )
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
