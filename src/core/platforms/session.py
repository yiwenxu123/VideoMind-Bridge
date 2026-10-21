"""平台登录态：来源解析、脱敏状态与可选健康检查。"""

from __future__ import annotations

import os
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol

import httpx

from .cookies import (
    build_cookie_header,
    cookie_summary,
    parse_netscape_cookies,
)

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class SessionStatus:
    platform: str
    configured: bool
    source: str
    cookie_count: int = 0
    expires_at: str | None = None
    valid: bool | None = None
    last_checked: str | None = None
    error_code: str | None = None
    warning: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SessionCheckUnsupported(RuntimeError):
    pass


class SessionProvider(Protocol):
    platform: str
    supports_check: bool

    def headers(self) -> dict[str, str]: ...

    def status(self) -> SessionStatus: ...

    def check(self) -> SessionStatus: ...

    def close(self) -> None: ...


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _cookie_file_warning(path: str) -> str | None:
    if os.name != "posix":
        return None
    try:
        mode = os.stat(os.path.expanduser(path)).st_mode
    except OSError:
        return None
    return "cookie_file_permissions" if mode & 0o077 else None


class BilibiliSessionProvider:
    platform = "bilibili"
    supports_check = True

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._http = http_client

    def _cookie_context(self) -> tuple[str, str, int, str | None, str | None]:
        raw = os.getenv("VMB_BILIBILI_COOKIE", "").strip()
        if raw:
            count = raw.count(";") + 1
            return raw, "env", count, None, None

        sessdata = os.getenv("VMB_BILIBILI_SESSDATA", "").strip()
        if sessdata:
            return f"SESSDATA={sessdata}", "env", 1, None, None

        path = (
            os.getenv("VMB_BILIBILI_COOKIES_FILE", "").strip()
            or os.getenv("VMB_COOKIES_FILE", "").strip()
        )
        if not path:
            return "", "none", 0, None, None

        records = parse_netscape_cookies(path, domain_suffix="bilibili.com")
        header = build_cookie_header(records)
        count, expires_at = cookie_summary(records)
        permission_warning = _cookie_file_warning(path)
        if header:
            return header, "file", count, expires_at, permission_warning
        return "", "file", 0, None, permission_warning or "no_valid_cookies"

    def headers(self) -> dict[str, str]:
        header, _, _, _, _ = self._cookie_context()
        return {"Cookie": header} if header else {}

    def status(self) -> SessionStatus:
        header, source, count, expires_at, warning = self._cookie_context()
        return SessionStatus(
            platform=self.platform,
            configured=bool(header),
            source=source,
            cookie_count=count,
            expires_at=expires_at,
            warning=warning,
        )

    def check(self) -> SessionStatus:
        status = self.status()
        if not status.configured:
            status.valid = False
            status.error_code = "auth_required"
            status.last_checked = _now_iso()
            return status

        headers = {
            "Cookie": self.headers()["Cookie"],
            "User-Agent": _DEFAULT_UA,
            "Referer": "https://www.bilibili.com",
        }
        try:
            if self._http is not None:
                response = self._http.get(
                    "https://api.bilibili.com/x/web-interface/nav",
                    headers=headers,
                    timeout=10.0,
                )
            else:
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(
                        "https://api.bilibili.com/x/web-interface/nav",
                        headers=headers,
                    )
            status.last_checked = _now_iso()
            if response.status_code == 401:
                status.valid = False
                status.error_code = "auth_required"
                return status
            if response.status_code in (403, 412):
                status.valid = False
                status.error_code = "risk_control"
                return status
            response.raise_for_status()
            data = response.json()
            code = data.get("code")
            if code == 0:
                is_login = bool((data.get("data") or {}).get("isLogin"))
                status.valid = is_login
                status.error_code = None if is_login else "auth_required"
            elif code == -101:
                status.valid = False
                status.error_code = "auth_required"
            elif code in (-352, -412, -799):
                status.valid = False
                status.error_code = "risk_control"
            else:
                status.valid = False
                status.error_code = "upstream_error"
            return status
        except httpx.HTTPError:
            status.valid = False
            status.error_code = "upstream_error"
            status.last_checked = _now_iso()
            return status

    def close(self) -> None:
        if self._http is not None:
            self._http.close()


class DouyinSessionProvider:
    platform = "douyin"
    supports_check = False

    def _cookie_context(self) -> tuple[str, str, int, str | None, str | None]:
        path = os.getenv("DOUYIN_COOKIES_FILE", "").strip()
        if not path:
            return "", "none", 0, None, None
        records = parse_netscape_cookies(path)
        header = build_cookie_header(records)
        count, expires_at = cookie_summary(records)
        if header:
            return header, "file", count, expires_at, None
        return "", "file", 0, None, "no_valid_cookies"

    def headers(self) -> dict[str, str]:
        header, _, _, _, _ = self._cookie_context()
        return {"Cookie": header} if header else {}

    def status(self) -> SessionStatus:
        header, source, count, expires_at, warning = self._cookie_context()
        return SessionStatus(
            platform=self.platform,
            configured=bool(header),
            source=source,
            cookie_count=count,
            expires_at=expires_at,
            warning=warning,
        )

    def check(self) -> SessionStatus:
        return self.status()

    def close(self) -> None:
        return None


class YtDlpSessionProvider:
    platform = "ytdlp"
    supports_check = False

    def _context(self) -> tuple[str, bool, int, str | None, str | None]:
        path = os.getenv("VMB_COOKIES_FILE", "").strip()
        if path:
            records = parse_netscape_cookies(path)
            count, expires_at = cookie_summary(records)
            return "file", bool(records), count, expires_at, None
        if os.getenv("VMB_COOKIES_BROWSER", "").strip():
            return "browser", True, 0, None, "browser_cookie_source"
        return "none", False, 0, None, None

    def headers(self) -> dict[str, str]:
        return {}

    def status(self) -> SessionStatus:
        source, configured, count, expires_at, warning = self._context()
        return SessionStatus(
            platform=self.platform,
            configured=configured,
            source=source,
            cookie_count=count,
            expires_at=expires_at,
            warning=warning,
        )

    def check(self) -> SessionStatus:
        return self.status()

    def close(self) -> None:
        return None


class NoneSessionProvider:
    supports_check = False

    def __init__(self, platform: str) -> None:
        self.platform = platform

    def headers(self) -> dict[str, str]:
        return {}

    def status(self) -> SessionStatus:
        return SessionStatus(
            platform=self.platform,
            configured=False,
            source="none",
        )

    def check(self) -> SessionStatus:
        return self.status()

    def close(self) -> None:
        return None


class SessionManager:
    def __init__(self, providers: list[SessionProvider] | None = None) -> None:
        self._providers = providers or [
            BilibiliSessionProvider(),
            DouyinSessionProvider(),
            YtDlpSessionProvider(),
            NoneSessionProvider("xiaohongshu"),
            NoneSessionProvider("youtube"),
        ]

    def get(self, platform: str) -> SessionProvider | None:
        for provider in self._providers:
            if provider.platform == platform:
                return provider
        return None

    def statuses(self) -> list[SessionStatus]:
        return [provider.status() for provider in self._providers]

    def check(self, platform: str) -> SessionStatus:
        provider = self.get(platform)
        if provider is None or not provider.supports_check:
            raise SessionCheckUnsupported(platform)
        return provider.check()

    def close(self) -> None:
        for provider in self._providers:
            provider.close()


_session_manager: SessionManager | None = None
_session_lock = threading.Lock()


def get_session_manager() -> SessionManager:
    global _session_manager
    with _session_lock:
        if _session_manager is None:
            _session_manager = SessionManager()
        return _session_manager


def reset_session_manager() -> None:
    global _session_manager
    with _session_lock:
        if _session_manager is not None:
            _session_manager.close()
        _session_manager = None
