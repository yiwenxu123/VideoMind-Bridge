"""平台级节流、重试与熔断测试。"""

from __future__ import annotations

import random
from typing import Any

import httpx
import pytest

from src.core.platforms.rate_limit import (
    PlatformPolicy,
    PlatformRateLimiter,
    PlatformRequestError,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class ZeroJitter(random.Random):
    def uniform(self, _start: float, _end: float) -> float:
        return 0.0


def _limiter(
    policy: PlatformPolicy | None = None,
    *,
    enabled: bool = True,
) -> tuple[PlatformRateLimiter, FakeClock]:
    clock = FakeClock()
    limiter = PlatformRateLimiter(
        {"bilibili": policy or PlatformPolicy()},
        enabled=enabled,
        clock=clock,
        sleep=clock.sleep,
        rng=ZeroJitter(),
    )
    return limiter, clock


def _status_error(status: int, headers: dict[str, str] | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.bilibili.com/x/test")
    response = httpx.Response(status, request=request, headers=headers or {})
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_disabled_limiter_calls_func_directly():
    limiter, _ = _limiter(enabled=False)
    calls: list[int] = []

    assert limiter.execute("bilibili", lambda: calls.append(1) or "ok") == "ok"
    assert calls == [1]


def test_pacing_waits_between_requests():
    limiter, clock = _limiter(PlatformPolicy(min_interval_ms=1000))

    limiter.execute("bilibili", lambda: "a")
    limiter.execute("bilibili", lambda: "b")

    assert clock.sleeps == [1.0]


def test_pacing_refuses_wait_beyond_max_wait():
    limiter, clock = _limiter(
        PlatformPolicy(min_interval_ms=5000, max_wait_seconds=1.0)
    )
    limiter.execute("bilibili", lambda: "a")

    with pytest.raises(PlatformRequestError) as exc_info:
        limiter.execute("bilibili", lambda: "b")

    assert exc_info.value.code == "rate_limited"
    assert clock.sleeps == []


def test_pacing_refuses_wait_beyond_deadline():
    limiter, clock = _limiter(PlatformPolicy(min_interval_ms=1000))
    limiter.execute("bilibili", lambda: "a")

    with pytest.raises(PlatformRequestError) as exc_info:
        limiter.execute("bilibili", lambda: "b", deadline=clock() + 0.2)

    assert exc_info.value.code == "rate_limited"


def test_retries_429_with_retry_after():
    limiter, clock = _limiter(PlatformPolicy(max_retries=1))
    calls: list[int] = []

    def func() -> str:
        calls.append(1)
        if len(calls) == 1:
            raise _status_error(429, {"Retry-After": "2"})
        return "ok"

    assert limiter.execute("bilibili", func) == "ok"
    assert len(calls) == 2
    assert clock.sleeps == [2.0]


def test_retries_5xx_with_backoff():
    limiter, clock = _limiter(
        PlatformPolicy(max_retries=1, backoff_base_ms=1000)
    )
    calls: list[int] = []

    def func() -> str:
        calls.append(1)
        if len(calls) == 1:
            raise _status_error(503)
        return "ok"

    assert limiter.execute("bilibili", func) == "ok"
    assert len(calls) == 2
    assert clock.sleeps == [1.0]


def test_risk_control_does_not_retry_and_opens_circuit():
    limiter, _ = _limiter(
        PlatformPolicy(max_retries=3, circuit_threshold=1)
    )
    calls: list[int] = []

    def func() -> str:
        calls.append(1)
        raise _status_error(412)

    with pytest.raises(PlatformRequestError) as exc_info:
        limiter.execute("bilibili", func)

    assert exc_info.value.code == "risk_control"
    assert len(calls) == 1
    assert limiter.circuit_state("bilibili") == "open"

    with pytest.raises(PlatformRequestError) as exc_info:
        limiter.execute("bilibili", func)
    assert exc_info.value.code == "risk_control"
    assert len(calls) == 1


def test_auth_required_does_not_retry():
    limiter, _ = _limiter(PlatformPolicy(max_retries=3))
    calls: list[int] = []

    def func() -> str:
        calls.append(1)
        raise _status_error(401)

    with pytest.raises(PlatformRequestError) as exc_info:
        limiter.execute("bilibili", func)

    assert exc_info.value.code == "auth_required"
    assert len(calls) == 1


def test_body_level_risk_notification_opens_circuit():
    limiter, _ = _limiter(PlatformPolicy(circuit_threshold=2))

    limiter.notify_risk_control("bilibili")
    assert limiter.circuit_state("bilibili") == "closed"

    limiter.notify_risk_control("bilibili")
    assert limiter.circuit_state("bilibili") == "open"

    with pytest.raises(PlatformRequestError) as exc_info:
        limiter.execute("bilibili", lambda: "never")
    assert exc_info.value.code == "risk_control"


def test_circuit_recovers_after_cooldown():
    limiter, clock = _limiter(
        PlatformPolicy(circuit_threshold=1, circuit_cooldown_seconds=10)
    )
    limiter.notify_risk_control("bilibili")
    assert limiter.circuit_state("bilibili") == "open"

    clock.now += 11
    assert limiter.circuit_state("bilibili") == "closed"
    assert limiter.execute("bilibili", lambda: "ok") == "ok"


def test_timeout_retries_then_raises_upstream_error():
    limiter, _ = _limiter(PlatformPolicy(max_retries=1, backoff_base_ms=10))
    calls: list[int] = []

    def func() -> Any:
        calls.append(1)
        raise httpx.ReadTimeout("slow")

    with pytest.raises(PlatformRequestError) as exc_info:
        limiter.execute("bilibili", func)

    assert exc_info.value.code == "upstream_error"
    assert len(calls) == 2
