"""Bilibili API 客户端：WBI 签名、cookie 加载与 HTTP 封装。

供 BilibiliExtractor 与 discovery provider 复用；不包含内容解析逻辑。
"""

from __future__ import annotations

import hashlib
import os
import time
import urllib.parse
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

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


class BilibiliApiError(RuntimeError):
    """Bilibili API 响应异常（非 HTTP 状态错误）。"""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


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
    try:
        lines = Path(path).expanduser().read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""

    current = time.time() if now is None else now
    cookies: list[str] = []
    for raw in lines:
        line = raw.strip()
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_") :]
        elif not line or line.startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain = parts[0].lstrip(".").lower()
        if domain_suffix:
            suffix = domain_suffix.lstrip(".").lower()
            if domain != suffix and not domain.endswith(f".{suffix}"):
                continue
        expiry, name, value = parts[4], parts[5], parts[6]
        try:
            expires = int(expiry)
        except ValueError:
            expires = 0
        if expires and expires < current:
            continue
        if name:
            cookies.append(f"{name}={value}")
    return "; ".join(cookies)


class BilibiliClient:
    """Bilibili HTTP + WBI 签名客户端。"""

    BASE_URL = "https://api.bilibili.com"

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        cookies_file: str | os.PathLike[str] | None = None,
        cookie_header: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._wbi_key: str | None = None
        headers = dict(_DEFAULT_HEADERS)
        file_cookie = (
            load_cookie_header(cookies_file, domain_suffix="bilibili.com")
            if cookies_file
            else ""
        )
        raw_cookie = (cookie_header or "").strip().strip(";").strip()
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

    def get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        url = path if path.startswith(("http://", "https://")) else f"{self.BASE_URL}{path}"
        request_headers = dict(self._headers)
        if headers:
            request_headers.update(headers)
        response = self._client.get(
            url,
            params=params,
            headers=request_headers,
            timeout=timeout,
        )
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError as exc:
            raise BilibiliApiError("响应不是合法 JSON") from exc
        if not isinstance(data, dict):
            raise BilibiliApiError("响应不是 JSON 对象")
        return data

    def get_wbi_key(self) -> str:
        if self._wbi_key is not None:
            return self._wbi_key

        try:
            data = self.get_json("/x/web-interface/nav")
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
    ) -> dict[str, str]:
        signed = {str(key): str(value) for key, value in params.items() if value is not None}
        signed["wts"] = str(int(time.time()))
        key = wbi_key or self.get_wbi_key()
        query = urllib.parse.urlencode(sorted(signed.items()))
        signed["w_rid"] = hashlib.md5((query + key).encode()).hexdigest()
        return signed

    def wbi_get(
        self,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return self.get_json(
            path,
            params=self.sign(params),
            headers=headers,
            timeout=timeout,
        )

    def resolve_url(
        self,
        url: str,
        *,
        max_redirects: int = 3,
        timeout: float | None = None,
    ) -> str | None:
        """解析 b23.tv 等短链；最多跟随 max_redirects 次，不自动接受任意域。"""
        current = url
        for _ in range(max_redirects + 1):
            response = self._client.get(
                current,
                headers=self._headers,
                follow_redirects=False,
                timeout=timeout,
            )
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    return None
                current = urljoin(current, location)
                continue
            return str(response.url)
        return None
