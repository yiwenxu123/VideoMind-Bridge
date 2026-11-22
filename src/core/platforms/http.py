"""平台自有 HTTP 请求的统一入口：节流、重试与错误映射。"""

from __future__ import annotations

from collections.abc import Callable
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
    circuit_key: str | None = None,
    validator: Callable[[httpx.Response], None] | None = None,
) -> httpx.Response:
    """对平台自有域名发起 GET，并经过平台级节流/退避/熔断。

    只用于平台自己的接口；本地网关、第三方 API 和 CDN 下载不应走这里。
    非 2xx 会抛 ``PlatformRequestError``，调用方按现有降级语义处理。

    ``circuit_key`` 用于把熔断隔离到平台内的具体链路（如 ``douyin:share``），
    不传则退化为按平台熔断（旧行为）。

    ``validator`` 允许调用方在 2xx 之后再做一次内容判定。典型用途：抖音/小红书会返回
    **HTTP 200 的验证码壳页**——状态码正常但内容不是目标页。validator 抛
    ``PlatformRequestError("risk_control", ...)`` 即可让本次请求记为失败并计入熔断，
    而不是被误记成 success。
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
        if validator is not None:
            validator(response)
        return response

    active_limiter = limiter or get_platform_rate_limiter()
    response: httpx.Response = active_limiter.execute(
        platform,
        _run,
        deadline=deadline,
        circuit_key=circuit_key,
    )
    return response
