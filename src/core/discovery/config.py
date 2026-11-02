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
DEFAULT_DISCOVERY_HTTP_TIMEOUT_SECONDS = 10
DEFAULT_DISCOVERY_TOTAL_TIMEOUT_SECONDS = 30
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
    """B 站 Cookie header —— 统一由 SessionManager 解析 (env/keyring/cookies 文件)。"""
    from ..platforms.session import get_session_manager

    provider = get_session_manager().get("bilibili")
    if provider is None:
        return None
    return provider.headers().get("Cookie") or None


def discovery_http_timeout() -> float:
    raw = os.getenv(
        "VMB_DISCOVERY_HTTP_TIMEOUT",
        str(DEFAULT_DISCOVERY_HTTP_TIMEOUT_SECONDS),
    )
    try:
        return max(1.0, float(raw))
    except ValueError:
        return float(DEFAULT_DISCOVERY_HTTP_TIMEOUT_SECONDS)


def discovery_total_timeout() -> float:
    raw = os.getenv(
        "VMB_DISCOVERY_TOTAL_TIMEOUT",
        str(DEFAULT_DISCOVERY_TOTAL_TIMEOUT_SECONDS),
    )
    try:
        return max(1.0, float(raw))
    except ValueError:
        return float(DEFAULT_DISCOVERY_TOTAL_TIMEOUT_SECONDS)
