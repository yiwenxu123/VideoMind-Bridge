"""平台直连 HTTP helper 的节流与错误映射测试。"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from src.core.platforms.http import platform_get
from src.core.platforms.rate_limit import (
    PlatformPolicy,
    PlatformRateLimiter,
    PlatformRequestError,
)


class RecordingLimiter(PlatformRateLimiter):
    def __init__(self) -> None:
        super().__init__({}, enabled=True)
        self.calls: list[tuple[str, float | None]] = []

    def execute(
        self,
        platform: str,
        func: Any,
        *,
        deadline: float | None = None,
    ) -> Any:
        self.calls.append((platform, deadline))
        return func()


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_platform_get_uses_limiter():
    limiter = RecordingLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://www.douyin.com/video/1"
        return httpx.Response(200, json={"ok": True})

    response = platform_get(
        "douyin",
        _client(handler),
        "https://www.douyin.com/video/1",
        limiter=limiter,  # type: ignore[arg-type]
    )

    assert response.json() == {"ok": True}
    assert limiter.calls == [("douyin", None)]


def test_platform_get_maps_risk_control_and_trips_circuit():
    limiter = PlatformRateLimiter(
        {"douyin": PlatformPolicy(circuit_threshold=1)}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(412, request=request)

    with pytest.raises(PlatformRequestError) as exc_info:
        platform_get(
            "douyin",
            _client(handler),
            "https://www.douyin.com/video/1",
            limiter=limiter,
        )

    assert exc_info.value.code == "risk_control"
    assert limiter.circuit_state("douyin") == "open"


def test_platform_get_does_not_retry_403():
    limiter = PlatformRateLimiter(
        {"douyin": PlatformPolicy(max_retries=3, circuit_threshold=10)}
    )
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(403, request=request)

    with pytest.raises(PlatformRequestError) as exc_info:
        platform_get(
            "douyin",
            _client(handler),
            "https://www.douyin.com/video/1",
            limiter=limiter,
        )

    assert exc_info.value.code == "risk_control"
    assert len(calls) == 1
