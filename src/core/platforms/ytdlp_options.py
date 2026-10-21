"""yt-dlp 子进程的网络节流、重试与 cookies 参数。"""

from __future__ import annotations

import os

from ...utils.platform_detector import detect_platform

_DEFAULT_SLEEP_SECONDS = {
    "bilibili": 1.0,
    "douyin": 2.0,
    "xiaohongshu": 1.5,
    "youtube": 0.5,
}
_DEFAULT_RETRIES = 3
_DEFAULT_EXTRACTOR_RETRIES = 2
_DEFAULT_SOCKET_TIMEOUT = 30.0


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def ytdlp_network_args(url: str) -> list[str]:
    """按平台生成 yt-dlp 的请求间隔、重试与 socket 超时参数。"""
    platform = detect_platform(url)
    sleep_seconds = _env_float(
        "VMB_YTDLP_SLEEP_REQUESTS",
        _DEFAULT_SLEEP_SECONDS.get(platform, 0.0),
    )
    args: list[str] = []
    if sleep_seconds > 0:
        args.extend(["--sleep-requests", f"{sleep_seconds:g}"])

    retries = _env_int("VMB_YTDLP_RETRIES", _DEFAULT_RETRIES)
    args.extend(["--retries", str(retries)])
    extractor_retries = _env_int(
        "VMB_YTDLP_EXTRACTOR_RETRIES",
        _DEFAULT_EXTRACTOR_RETRIES,
    )
    args.extend(["--extractor-retries", str(extractor_retries)])

    socket_timeout = _env_float(
        "VMB_YTDLP_SOCKET_TIMEOUT",
        _DEFAULT_SOCKET_TIMEOUT,
    )
    args.extend(["--socket-timeout", f"{socket_timeout:g}"])

    sleep_interval = _env_float("VMB_YTDLP_SLEEP_INTERVAL", 0.0)
    if sleep_interval > 0:
        args.extend(["--sleep-interval", f"{sleep_interval:g}"])
    return args


def ytdlp_cookie_args() -> list[str]:
    """通过 YtDlpSessionProvider 统一生成 cookies 参数。"""
    from .session import YtDlpSessionProvider, get_session_manager

    provider = get_session_manager().get("ytdlp")
    if isinstance(provider, YtDlpSessionProvider):
        return provider.cookie_args()
    return []
