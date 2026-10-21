"""平台自有 HTTP 请求的统一入口：节流、重试与错误映射。"""

from __future__ import annotations

from typing import Any

import httpx

from .rate_limit import PlatformRateLimiter, get_platform_rate_limiter


def platform_get(
    platform: str,
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float | None = None,
    follow_redirects: bool | None = None,
    deadline: float | None = None,
    limiter: PlatformRateLimiter | None = None,
) -> httpx.Response:
    """对平台自有域名发起 GET，并经过平台级节流/退避/熔断。

    只用于平台自己的接口；本地网关、第三方 API 和 CDN 下载不应走这里。
    非 2xx 会抛 ``PlatformRequestError``，调用方按现有降级语义处理。
    """

    def _run() -> httpx.Response:
        kwargs: dict[str, Any] = {}
        if headers is not None:
            kwargs["headers"] = headers
        if params is not None:
            kwargs["params"] = params
        if timeout is not None:
            kwargs["timeout"] = timeout
        if follow_redirects is not None:
            kwargs["follow_redirects"] = follow_redirects
        response = client.get(url, **kwargs)
        response.raise_for_status()
        return response

    active_limiter = limiter or get_platform_rate_limiter()
    response: httpx.Response = active_limiter.execute(
        platform,
        _run,
        deadline=deadline,
    )
    return response
