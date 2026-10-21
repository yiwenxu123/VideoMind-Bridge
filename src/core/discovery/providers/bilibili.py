"""Bilibili 创作者作品与评论 provider。"""

from __future__ import annotations

import html
import os
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from ...models import CostTier
from ...platforms.bilibili_client import BilibiliApiError, BilibiliClient
from ..base import DiscoveryProvider
from ..config import (
    COMMENT_TEXT_MAX_CHARS,
    MAX_REPLY_THREADS,
    bilibili_cookie_header,
    bilibili_min_interval_ms,
    discovery_http_timeout,
    discovery_total_timeout,
)
from ..models import (
    CommentItem,
    CommentsResult,
    CreatorFeedItem,
    CreatorFeedResult,
    CreatorRef,
    DiscoveryError,
)
from ..throttle import PlatformThrottle

_MID_RE = re.compile(r"^/(\d+)")
_SPACE_MID_RE = re.compile(r"^/space/(\d+)")
_BV_RE = re.compile(r"/video/(BV[0-9A-Za-z]+)")
_AV_RE = re.compile(r"/video/av(\d+)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")

_COMMENT_PAGE_SIZE = 20
_MAX_COMMENT_PAGES = 3

_METRIC_KEYS = {
    "view": "views",
    "like": "likes",
    "reply": "comments",
    "favorite": "favorites",
    "coin": "coins",
    "share": "shares",
}


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _clean_text(value: Any) -> str:
    return html.unescape(_TAG_RE.sub("", str(value or ""))).strip()


def _iso_timestamp(value: Any) -> str | None:
    timestamp = _as_int(value)
    if timestamp is None or timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat(timespec="seconds")


def _parse_duration(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0.0, float(value))
    if not isinstance(value, str):
        return 0.0
    parts = value.strip().split(":")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return 0.0
    if len(numbers) == 2:
        return float(numbers[0] * 60 + numbers[1])
    if len(numbers) == 3:
        return float(numbers[0] * 3600 + numbers[1] * 60 + numbers[2])
    return 0.0


def _normalize_url(value: Any) -> str | None:
    url = str(value or "").strip()
    if not url:
        return None
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("http://"):
        return f"https://{url[len('http://') :]}"
    if url.startswith("https://"):
        return url
    return None


def _append_warning(warnings: list[str], value: str) -> None:
    if value not in warnings:
        warnings.append(value)


class BilibiliDiscoveryProvider(DiscoveryProvider):
    platform = "bilibili"
    source_name = "bilibili_discovery"
    _cost_tier = CostTier.FREE

    def __init__(
        self,
        client: BilibiliClient | None = None,
        throttle: PlatformThrottle | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        http_timeout: float | None = None,
        total_timeout: float | None = None,
    ) -> None:
        cookies_file = (
            os.getenv("VMB_BILIBILI_COOKIES_FILE")
            or os.getenv("VMB_COOKIES_FILE")
            or None
        )
        self._clock = clock
        self._http_timeout = (
            http_timeout if http_timeout is not None else discovery_http_timeout()
        )
        self._total_timeout = (
            total_timeout if total_timeout is not None else discovery_total_timeout()
        )
        self._client = client or BilibiliClient(
            cookies_file=cookies_file,
            cookie_header=bilibili_cookie_header(),
            timeout=self._http_timeout,
        )
        self._throttle = throttle or PlatformThrottle(
            {"bilibili": bilibili_min_interval_ms()}
        )

    # ── creator feed ─────────────────────────────────────────────

    def supports_creator_url(self, url: str) -> bool:
        return self._extract_mid(url) is not None

    def fetch_creator_feed(self, url: str, limit: int) -> CreatorFeedResult:
        mid = self._extract_mid(url)
        if mid is None:
            raise DiscoveryError("invalid_request", "无法从 URL 解析 B站创作者 UID")

        params = {
            "mid": mid,
            "ps": str(limit),
            "pn": "1",
            "order": "pubdate",
            "platform": "web",
            "web_location": "1550101",
        }
        headers = {
            "Referer": f"https://space.bilibili.com/{mid}",
            "Origin": "https://space.bilibili.com",
        }
        payload = self._request_json(
            "/x/space/wbi/arc/search",
            params,
            wbi=True,
            headers=headers,
            not_found_code="creator_not_found",
        )

        data = payload.get("data")
        if not isinstance(data, dict):
            raise DiscoveryError("upstream_error", "B站返回结构异常")

        list_data = data.get("list")
        if list_data is None:
            vlist: list[Any] = []
        elif isinstance(list_data, dict):
            raw_vlist = list_data.get("vlist")
            if raw_vlist is None:
                vlist = []
            elif isinstance(raw_vlist, list):
                vlist = raw_vlist
            else:
                raise DiscoveryError("upstream_error", "B站作品列表结构异常")
        else:
            raise DiscoveryError("upstream_error", "B站作品列表结构异常")

        items: list[CreatorFeedItem] = []
        for raw in vlist[:limit]:
            if isinstance(raw, dict):
                item = self._parse_item(raw)
                if item is not None:
                    items.append(item)

        creator_name = ""
        for entry in vlist:
            if isinstance(entry, dict):
                creator_name = _clean_text(entry.get("author"))
                if creator_name:
                    break
        if not creator_name:
            card = data.get("card")
            if isinstance(card, dict):
                creator_name = _clean_text(card.get("name"))

        page = data.get("page")
        total = _as_int(page.get("count")) if isinstance(page, dict) else None
        has_more = total > len(items) if total is not None else len(vlist) >= limit

        warnings: list[str] = []
        if not creator_name:
            warnings.append("creator_name_unavailable")

        return CreatorFeedResult(
            success=True,
            platform=self.platform,
            source=self.source_name,
            cost_tier=self._cost_tier,
            creator=CreatorRef(
                id=mid,
                name=creator_name,
                url=f"https://space.bilibili.com/{mid}",
            ),
            items=items,
            completeness="full",
            has_more=has_more,
            warnings=warnings,
        )

    # ── comments ─────────────────────────────────────────────────

    def supports_comments(self, url: str) -> bool:
        return self._is_b23_url(url) or self._extract_video_ids(url) is not None

    def fetch_comments(
        self,
        url: str,
        *,
        limit: int,
        sort: str,
        include_replies: bool,
        max_replies_per_thread: int,
        include_author: bool,
    ) -> CommentsResult:
        if sort not in {"hot", "recent"}:
            raise DiscoveryError("invalid_request", "sort 必须是 hot 或 recent")

        deadline = self._clock() + self._total_timeout

        if self._is_b23_url(url):
            left = deadline - self._clock()
            if left <= 0:
                raise DiscoveryError("upstream_error", "评论采集总超时")
            self._throttle.acquire(self.platform)
            resolved = self._client.resolve_url(
                url,
                max_redirects=3,
                timeout=max(1.0, min(self._http_timeout, left)),
            )
            if not resolved:
                raise DiscoveryError("content_not_found", "B站短链解析失败")
            resolved_host = (urlsplit(resolved).hostname or "").lower()
            if resolved_host not in {"www.bilibili.com", "bilibili.com", "m.bilibili.com"}:
                raise DiscoveryError("content_not_found", "B站短链未指向视频页")
            url = resolved

        video = self._extract_video_ids(url)
        if video is None:
            raise DiscoveryError("invalid_request", "无法从 URL 解析 B站视频 ID")
        bvid, aid = video
        if aid is None:
            left = deadline - self._clock()
            if left <= 0:
                raise DiscoveryError("upstream_error", "评论采集总超时")
            view = self._request_json(
                "/x/web-interface/view",
                {"bvid": bvid},
                wbi=True,
                not_found_code="content_not_found",
                timeout=max(1.0, min(self._http_timeout, left)),
            )
            data = view.get("data")
            if not isinstance(data, dict):
                raise DiscoveryError("upstream_error", "B站返回结构异常")
            aid = _as_int(data.get("aid"))
        if aid is None:
            raise DiscoveryError("upstream_error", "无法解析 B站视频 aid")

        sort_value = "2" if sort == "hot" else "0"
        max_pages = min(
            _MAX_COMMENT_PAGES,
            max(1, (limit + _COMMENT_PAGE_SIZE - 1) // _COMMENT_PAGE_SIZE),
        )

        items: list[CommentItem] = []
        warnings: list[str] = []
        total_count = 0
        top_level_returned = 0

        for page_number in range(1, max_pages + 1):
            left = deadline - self._clock()
            if left <= 0:
                _append_warning(warnings, "total_timeout")
                break
            try:
                payload = self._request_json(
                    "/x/v2/reply",
                    {
                        "type": "1",
                        "oid": str(aid),
                        "sort": sort_value,
                        "pn": str(page_number),
                        "ps": str(_COMMENT_PAGE_SIZE),
                    },
                    not_found_code="content_not_found",
                    timeout=max(1.0, min(self._http_timeout, left)),
                )
            except DiscoveryError:
                if items:
                    _append_warning(warnings, "page_fetch_partial")
                    break
                raise
            data = payload.get("data")
            if not isinstance(data, dict):
                raise DiscoveryError("upstream_error", "B站评论结构异常")
            replies = data.get("replies")
            if replies is None:
                replies = []
            if not isinstance(replies, list):
                raise DiscoveryError("upstream_error", "B站评论列表结构异常")

            page = data.get("page")
            if isinstance(page, dict):
                page_count = _as_int(page.get("count"))
                if page_count is not None:
                    total_count = page_count

            for raw in replies:
                if len(items) >= limit:
                    break
                if not isinstance(raw, dict):
                    continue
                item = self._parse_comment(
                    raw,
                    is_reply=False,
                    include_author=include_author,
                )
                if item is not None:
                    items.append(item)
                    top_level_returned += 1

            if len(items) >= limit or len(replies) < _COMMENT_PAGE_SIZE:
                break

        if not items and "total_timeout" in warnings:
            raise DiscoveryError("upstream_error", "评论采集总超时")

        if include_replies and len(items) < limit:
            top_level_items = [item for item in items if not item.is_reply]
            threads = [item for item in top_level_items if item.reply_count > 0]
            if len(threads) > MAX_REPLY_THREADS:
                _append_warning(warnings, "reply_threads_truncated")

            for top in threads[:MAX_REPLY_THREADS]:
                if len(items) >= limit:
                    break
                left = deadline - self._clock()
                if left <= 0:
                    _append_warning(warnings, "total_timeout")
                    break
                try:
                    payload = self._request_json(
                        "/x/v2/reply/reply",
                        {
                            "type": "1",
                            "oid": str(aid),
                            "root": top.id,
                            "pn": "1",
                            "ps": str(max_replies_per_thread),
                        },
                        not_found_code="content_not_found",
                        timeout=max(1.0, min(self._http_timeout, left)),
                    )
                except DiscoveryError as exc:
                    _append_warning(warnings, "reply_fetch_partial")
                    if exc.code in {"auth_required", "rate_limited", "risk_control"}:
                        break
                    continue

                data = payload.get("data")
                if not isinstance(data, dict):
                    _append_warning(warnings, "reply_fetch_partial")
                    continue
                replies = data.get("replies")
                if replies is None:
                    replies = []
                if not isinstance(replies, list):
                    _append_warning(warnings, "reply_fetch_partial")
                    continue

                returned = 0
                for raw in replies[:max_replies_per_thread]:
                    if len(items) >= limit:
                        break
                    if not isinstance(raw, dict):
                        continue
                    item = self._parse_comment(
                        raw,
                        is_reply=True,
                        include_author=include_author,
                    )
                    if item is not None:
                        items.append(item)
                        returned += 1

                if top.reply_count > returned:
                    _append_warning(warnings, "replies_truncated")

        has_more = total_count > top_level_returned
        if any(
            warning in warnings
            for warning in (
                "replies_truncated",
                "reply_threads_truncated",
                "reply_fetch_partial",
                "total_timeout",
                "page_fetch_partial",
            )
        ):
            has_more = True

        return CommentsResult(
            success=True,
            platform=self.platform,
            source=self.source_name,
            cost_tier=self._cost_tier,
            items=items,
            completeness="partial" if warnings else "full",
            sort=sort,
            has_more=has_more,
            warnings=warnings,
        )

    # ── request / error mapping ──────────────────────────────────

    def _request_json(
        self,
        path: str,
        params: dict[str, Any],
        *,
        wbi: bool = False,
        headers: dict[str, str] | None = None,
        not_found_code: str,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        self._throttle.acquire(self.platform)
        try:
            if wbi:
                payload = self._client.wbi_get(
                    path,
                    params,
                    headers=headers,
                    timeout=timeout,
                )
            else:
                payload = self._client.get_json(
                    path,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                )
        except httpx.TimeoutException as exc:
            raise DiscoveryError("upstream_error", "B站请求超时") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 401:
                raise DiscoveryError(
                    "auth_required",
                    "B站接口需要登录 Cookie；请配置 VMB_BILIBILI_COOKIES_FILE",
                ) from exc
            if status_code in (403, 412):
                raise DiscoveryError(
                    "risk_control",
                    "B站接口触发风控；请配置 VMB_BILIBILI_COOKIES_FILE 后重试",
                    retry_after_seconds=60,
                ) from exc
            if status_code == 404:
                raise DiscoveryError(not_found_code, "B站内容不存在") from exc
            if status_code == 429:
                raise DiscoveryError(
                    "rate_limited",
                    "B站接口限流",
                    retry_after_seconds=60,
                ) from exc
            raise DiscoveryError(
                "upstream_error",
                f"B站接口 HTTP {status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            raise DiscoveryError("upstream_error", f"B站请求失败: {exc}") from exc
        except BilibiliApiError as exc:
            raise DiscoveryError("upstream_error", str(exc)) from exc

        code = _as_int(payload.get("code"))
        if code == 0:
            return payload

        message = str(payload.get("message") or "B站接口返回错误")
        if code == -401:
            raise DiscoveryError(
                "auth_required",
                "B站接口需要登录 Cookie；请配置 VMB_BILIBILI_COOKIES_FILE",
            )
        if code in (-352, -412, -799):
            raise DiscoveryError(
                "risk_control",
                "B站接口触发风控；请配置 VMB_BILIBILI_COOKIES_FILE 后重试",
                retry_after_seconds=60,
            )
        if code in (-404, 404):
            raise DiscoveryError(not_found_code, f"B站内容不存在: {message}")
        raise DiscoveryError("upstream_error", f"B站接口错误 {code}: {message}")

    # ── URL / parsing helpers ────────────────────────────────────

    def _extract_mid(self, url: str) -> str | None:
        parsed = self._parse_url(url)
        if parsed is None:
            return None
        host = (parsed.hostname or "").lower()
        path = parsed.path or ""
        if host == "space.bilibili.com":
            match = _MID_RE.match(path)
            return match.group(1) if match else None
        if host in {"www.bilibili.com", "bilibili.com", "m.bilibili.com"} and path.startswith(
            "/space/"
        ):
            match = _SPACE_MID_RE.match(path)
            return match.group(1) if match else None
        return None

    def _is_b23_url(self, url: str) -> bool:
        parsed = self._parse_url(url)
        if parsed is None:
            return False
        return (
            (parsed.hostname or "").lower() == "b23.tv"
            and bool(parsed.path and parsed.path != "/")
        )

    def _extract_video_ids(self, url: str) -> tuple[str | None, int | None] | None:
        parsed = self._parse_url(url)
        if parsed is None:
            return None
        host = (parsed.hostname or "").lower()
        if host not in {"www.bilibili.com", "bilibili.com", "m.bilibili.com"}:
            return None
        path = parsed.path or ""
        match = _BV_RE.search(path)
        if match:
            return match.group(1), None
        match = _AV_RE.search(path)
        if match:
            return None, int(match.group(1))
        return None

    @staticmethod
    def _parse_url(url: str):
        try:
            parsed = urlsplit(url)
        except ValueError:
            return None
        if parsed.scheme not in {"http", "https"}:
            return None
        return parsed

    def _parse_item(self, raw: dict[str, Any]) -> CreatorFeedItem | None:
        bvid = str(raw.get("bvid") or "").strip()
        aid = _as_int(raw.get("aid"))
        if bvid:
            item_id = bvid
            item_url = f"https://www.bilibili.com/video/{bvid}"
        elif aid is not None:
            item_id = str(aid)
            item_url = f"https://www.bilibili.com/video/av{aid}"
        else:
            return None

        stat = raw.get("stat")
        metrics: dict[str, int] = {}
        if isinstance(stat, dict):
            for source_key, target_key in _METRIC_KEYS.items():
                value = _as_int(stat.get(source_key))
                if value is not None:
                    metrics[target_key] = value

        duration_value = raw.get("duration")
        if duration_value is None:
            duration_value = raw.get("length")

        return CreatorFeedItem(
            id=item_id,
            url=item_url,
            title=_clean_text(raw.get("title")),
            published_at=_iso_timestamp(raw.get("created")),
            duration_seconds=_parse_duration(duration_value),
            metrics=metrics,
            cover_url=_normalize_url(raw.get("pic")),
        )

    def _parse_comment(
        self,
        raw: dict[str, Any],
        *,
        is_reply: bool,
        include_author: bool,
    ) -> CommentItem | None:
        rpid = str(raw.get("rpid_str") or raw.get("rpid") or "").strip()
        if not rpid:
            return None

        content = raw.get("content")
        message = content.get("message") if isinstance(content, dict) else ""
        text = str(message or "").strip()
        truncated = len(text) > COMMENT_TEXT_MAX_CHARS
        if truncated:
            text = text[:COMMENT_TEXT_MAX_CHARS]

        root = _as_int(raw.get("root")) or 0
        parent = _as_int(raw.get("parent")) or 0
        author_name: str | None = None
        if include_author:
            member = raw.get("member")
            if isinstance(member, dict):
                author_name = _clean_text(member.get("uname")) or None

        return CommentItem(
            id=rpid,
            parent_id=str(parent) if parent else None,
            root_id=str(root) if root else rpid,
            text=text,
            likes=_as_int(raw.get("like")) or 0,
            created_at=_iso_timestamp(raw.get("ctime")),
            is_reply=is_reply,
            reply_count=_as_int(raw.get("rcount")) or 0,
            author_display_name=author_name,
            truncated=truncated,
        )
