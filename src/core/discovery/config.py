"""Discovery API 配置与默认值。"""

from __future__ import annotations

import os

DEFAULT_CREATOR_FEED_LIMIT = 20
MAX_CREATOR_FEED_LIMIT = 30
CREATOR_FEED_CACHE_TTL_SECONDS = 300
DEFAULT_COMMENTS_LIMIT = 20
MAX_COMMENTS_LIMIT = 50
DEFAULT_REPLIES_PER_THREAD = 3
MAX_REPLIES_PER_THREAD = 10
MAX_REPLY_THREADS = 10
COMMENTS_CACHE_TTL_SECONDS = 900
COMMENT_TEXT_MAX_CHARS = 2000
DEFAULT_BILIBILI_MIN_INTERVAL_MS = 1000
CREATOR_FEED_PLATFORMS = ("bilibili",)
COMMENTS_PLATFORMS = ("bilibili",)

_TRUTHY = {"1", "true", "yes", "on"}


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUTHY


def creator_feed_enabled() -> bool:
    return _env_truthy("VMB_ENABLE_CREATOR_FEED")


def comments_enabled() -> bool:
    return _env_truthy("VMB_ENABLE_COMMENTS")


def creator_feed_cache_ttl() -> int:
    raw = os.getenv("VMB_CREATOR_FEED_CACHE_TTL", str(CREATOR_FEED_CACHE_TTL_SECONDS))
    try:
        return max(0, int(raw))
    except ValueError:
        return CREATOR_FEED_CACHE_TTL_SECONDS


def comments_cache_ttl() -> int:
    raw = os.getenv("VMB_COMMENTS_CACHE_TTL", str(COMMENTS_CACHE_TTL_SECONDS))
    try:
        return max(0, int(raw))
    except ValueError:
        return COMMENTS_CACHE_TTL_SECONDS


def bilibili_cookie_header() -> str | None:
    """完整 Cookie header 优先；否则由 SESSDATA 拼装。"""
    raw = os.getenv("VMB_BILIBILI_COOKIE", "").strip()
    if raw:
        return raw
    sessdata = os.getenv("VMB_BILIBILI_SESSDATA", "").strip()
    return f"SESSDATA={sessdata}" if sessdata else None


def bilibili_min_interval_ms() -> int:
    raw = os.getenv(
        "VMB_BILIBILI_MIN_INTERVAL_MS",
        str(DEFAULT_BILIBILI_MIN_INTERVAL_MS),
    )
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_BILIBILI_MIN_INTERVAL_MS


def platform_min_intervals() -> dict[str, int]:
    return {"bilibili": bilibili_min_interval_ms()}
