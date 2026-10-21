"""Bilibili API 客户端：WBI 签名、cookie 加载与 HTTP 封装。

供 BilibiliExtractor 与 discovery provider 复用；不包含内容解析逻辑。
"""

from __future__ import annotations

import hashlib
import os
import time
import urllib.parse
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin

import httpx

from .cookies import build_cookie_header, parse_netscape_cookies
from .rate_limit import (
    PlatformRateLimiter,
    PlatformRequestError,
    get_platform_rate_limiter,
)
from .session import SessionProvider

MIXIN_KEY_ENC_TABLE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 37, 12, 52, 56, 7,
    0, 16, 22, 38, 59, 55, 11, 61, 34, 40, 26, 17, 51, 41, 60, 39,
    20, 13, 48, 6, 36, 24, 44, 25, 21, 4, 54, 57, 30, 1,
]

# 默认 WBI 密钥 (当 API 获取失败时使用)
_FALLBACK_WBI_KEY = "ea1db124afe2e5b2"

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}

_BODY_RISK_CODES = {-352, -412, -799}


class BilibiliApiError(RuntimeError):
    """Bilibili API 响应异常（非 HTTP 状态错误）。"""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        status_code: int | None = None,
        error_code: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.error_code = error_code
        self.retry_after_seconds = retry_after_seconds


def load_cookie_header(
    path: str | os.PathLike[str],
    *,
    now: float | None = None,
    domain_suffix: str | None = None,
) -> str:
    """读取 Netscape cookies.txt，拼装为 Cookie header。

    支持 `#HttpOnly_` 前缀；跳过注释、格式错误和已过期 cookie。
    `domain_suffix` 非空时只保留该域及其子域的 cookie，避免把其他站点凭证发给目标平台。
    """
    records = parse_netscape_cookies(
        path,
        now=now,
        domain_suffix=domain_suffix,
    )
    return build_cookie_header(records)


class BilibiliClient:
    """Bilibili HTTP + WBI 签名客户端。"""

    BASE_URL = "https://api.bilibili.com"
    PLATFORM = "bilibili"

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        cookies_file: str | os.PathLike[str] | None = None,
        cookie_header: str | None = None,
        session: SessionProvider | None = None,
        client: httpx.Client | None = None,
        limiter: PlatformRateLimiter | None = None,
    ) -> None:
        self._wbi_key: str | None = None
        self._limiter = limiter or get_platform_rate_limiter()
        headers = dict(_DEFAULT_HEADERS)
        file_cookie = (
            load_cookie_header(cookies_file, domain_suffix="bilibili.com")
            if cookies_file
            else ""
        )
        raw_cookie = cookie_header
        if raw_cookie is None and cookies_file is None and session is not None:
            raw_cookie = session.headers().get("Cookie", "")
        raw_cookie = (raw_cookie or "").strip().strip(";").strip()
        raw_cookie = raw_cookie.replace("\r", " ").replace("\n", " ")
        cookie_parts = [part for part in (file_cookie, raw_cookie) if part]
        if cookie_parts:
            headers["Cookie"] = "; ".join(cookie_parts)
        self._headers = headers
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout,
            headers=headers,
        )

    @property
    def client(self) -> httpx.Client:
        return self._client

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        deadline: float | None = None,
        follow_redirects: bool = False,
    ) -> httpx.Response:
        return self._request(
            path,
            params=params,
            headers=headers,
            timeout=timeout,
            deadline=deadline,
            follow_redirects=follow_redirects,
        )

    def _request(
        self,
        path: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
        timeout: float | None,
        deadline: float | None,
        follow_redirects: bool,
        validate: Callable[[httpx.Response], None] | None = None,
    ) -> httpx.Response:
        url = path if path.startswith(("http://", "https://")) else f"{self.BASE_URL}{path}"
        request_headers = dict(self._headers)
        if headers:
            request_headers.update(headers)

        def _run() -> httpx.Response:
            response = self._client.get(
                url,
                params=params,
                headers=request_headers,
                timeout=timeout,
                follow_redirects=follow_redirects,
            )
            response.raise_for_status()
            if validate is not None:
                # 在 limiter 记录成功之前校验响应体，风控信号才能连续累计
                validate(response)
            return response

        try:
            response: httpx.Response = self._limiter.execute(
                self.PLATFORM,
                _run,
                deadline=deadline,
            )
            return response
        except PlatformRequestError as exc:
            raise BilibiliApiError(
                exc.message,
                status_code=exc.status_code,
                error_code=exc.code,
                retry_after_seconds=exc.retry_after_seconds,
            ) from exc

    def get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        parsed: dict[str, Any] = {}

        def _validate(response: httpx.Response) -> None:
            try:
                data = response.json()
            except ValueError as exc:
                raise BilibiliApiError("响应不是合法 JSON") from exc
            if not isinstance(data, dict):
                raise BilibiliApiError("响应不是 JSON 对象")
            code = data.get("code")
            if (
                isinstance(code, int)
                and not isinstance(code, bool)
                and code in _BODY_RISK_CODES
            ):
                self._limiter.notify_risk_control(self.PLATFORM)
                raise BilibiliApiError(
                    f"B站接口触发风控: {data.get('message') or code}",
                    code=code,
                    error_code="risk_control",
                    retry_after_seconds=60,
                )
            parsed.update(data)

        self._request(
            path,
            params=params,
            headers=headers,
            timeout=timeout,
            deadline=deadline,
            follow_redirects=False,
            validate=_validate,
        )
        return parsed

    def get_wbi_key(self, *, deadline: float | None = None) -> str:
        if self._wbi_key is not None:
            return self._wbi_key

        try:
            data = self.get_json("/x/web-interface/nav", deadline=deadline)
            wbi_img = (data.get("data") or {}).get("wbi_img") or {}
            img_url = str(wbi_img.get("img_url") or "")
            sub_url = str(wbi_img.get("sub_url") or "")
            if data.get("code") == 0 and img_url and sub_url:
                img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
                sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
                self._wbi_key = self.mixin_key(img_key + sub_key)
                return self._wbi_key
        except Exception:
            pass

        self._wbi_key = _FALLBACK_WBI_KEY
        return self._wbi_key

    @staticmethod
    def mixin_key(orig: str) -> str:
        return "".join(orig[i] for i in MIXIN_KEY_ENC_TABLE if i < len(orig))[:32]

    def sign(
        self,
        params: dict[str, Any],
        *,
        wbi_key: str | None = None,
        deadline: float | None = None,
    ) -> dict[str, str]:
        signed = {str(key): str(value) for key, value in params.items() if value is not None}
        signed["wts"] = str(int(time.time()))
        key = wbi_key or self.get_wbi_key(deadline=deadline)
        query = urllib.parse.urlencode(sorted(signed.items()))
        signed["w_rid"] = hashlib.md5((query + key).encode()).hexdigest()
        return signed

    def wbi_get(
        self,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        return self.get_json(
            path,
            params=self.sign(params, deadline=deadline),
            headers=headers,
            timeout=timeout,
            deadline=deadline,
        )

    def resolve_url(
        self,
        url: str,
        *,
        max_redirects: int = 3,
        timeout: float | None = None,
        deadline: float | None = None,
    ) -> str | None:
        """解析 b23.tv 等短链；最多跟随 max_redirects 次，不自动接受任意域。"""
        current = url
        for _ in range(max_redirects + 1):
            response = self.get(
                current,
                timeout=timeout,
                deadline=deadline,
                follow_redirects=False,
            )
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    return None
                current = urljoin(current, location)
                continue
            return str(response.url)
        return None
