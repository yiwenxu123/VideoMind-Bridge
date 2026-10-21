"""平台级节流、重试与熔断测试。"""

from __future__ import annotations

import logging
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


def test_from_env_scales_max_wait_with_interval(monkeypatch):
    monkeypatch.setenv(
        "VMB_PLATFORM_INTERVALS_MS",
        '{"bilibili": 1000, "douyin": 2000}',
    )
    monkeypatch.delenv("VMB_PLATFORM_MAX_WAIT_SECONDS", raising=False)

    limiter = PlatformRateLimiter.from_env()

    assert limiter._policy("bilibili").max_wait_seconds == 2.0
    assert limiter._policy("douyin").max_wait_seconds == 3.0


def test_from_env_respects_explicit_max_wait(monkeypatch):
    monkeypatch.setenv("VMB_PLATFORM_INTERVALS_MS", '{"douyin": 2000}')
    monkeypatch.setenv("VMB_PLATFORM_MAX_WAIT_SECONDS", "7")

    limiter = PlatformRateLimiter.from_env()

    assert limiter._policy("douyin").max_wait_seconds == 7.0


def test_metrics_snapshot_counts_success_and_latency():
    limiter, clock = _limiter(PlatformPolicy())

    def func() -> str:
        clock.sleep(0.25)
        return "ok"

    limiter.execute("bilibili", func)
    metrics = limiter.metrics_snapshot()["bilibili"]

    assert metrics["requests_total"] == 1
    assert metrics["success_total"] == 1
    assert metrics["failure_total"] == 0
    assert metrics["retries_total"] == 0
    assert metrics["latency_ms_avg"] == 250.0
    assert metrics["circuit"] == "closed"


def test_metrics_count_risk_outcomes_and_circuit_rejections():
    limiter, _ = _limiter(
        PlatformPolicy(max_retries=0, circuit_threshold=2)
    )

    def fail() -> str:
        raise _status_error(412)

    for _ in range(2):
        with pytest.raises(PlatformRequestError):
            limiter.execute("bilibili", fail)

    with pytest.raises(PlatformRequestError):
        limiter.execute("bilibili", fail)

    metrics = limiter.metrics_snapshot()["bilibili"]
    assert metrics["requests_total"] == 2
    assert metrics["failure_total"] == 2
    assert metrics["risk_control_total"] == 2
    assert metrics["circuit_open_total"] == 1
    assert metrics["circuit_rejected_total"] == 1
    assert metrics["circuit"] == "open"


def test_metrics_count_retries_and_final_success():
    limiter, _ = _limiter(PlatformPolicy(max_retries=1))
    calls: list[int] = []

    def func() -> str:
        calls.append(1)
        if len(calls) == 1:
            raise _status_error(429, {"Retry-After": "1"})
        return "ok"

    limiter.execute("bilibili", func)
    metrics = limiter.metrics_snapshot()["bilibili"]

    assert metrics["requests_total"] == 1
    assert metrics["success_total"] == 1
    assert metrics["retries_total"] == 1
    assert metrics["rate_limited_total"] == 0


def test_metrics_map_client_error_code():
    class ClientError(RuntimeError):
        error_code = "risk_control"
        status_code = 200

    limiter, _ = _limiter(PlatformPolicy(max_retries=0))

    with pytest.raises(ClientError):
        limiter.execute("bilibili", lambda: (_ for _ in ()).throw(ClientError()))

    metrics = limiter.metrics_snapshot()["bilibili"]
    assert metrics["requests_total"] == 1
    assert metrics["failure_total"] == 1
    assert metrics["risk_control_total"] == 1


def test_metrics_count_body_risk_signals():
    limiter, _ = _limiter(PlatformPolicy(circuit_threshold=2))

    limiter.notify_risk_control("bilibili")

    metrics = limiter.metrics_snapshot()["bilibili"]
    assert metrics["risk_control_signals_total"] == 1
    assert metrics["circuit"] == "closed"


def test_structured_log_has_platform_fields_without_url(caplog):
    limiter, _ = _limiter(PlatformPolicy())

    with caplog.at_level(
        logging.INFO,
        logger="src.core.platforms.rate_limit",
    ):
        limiter.execute("bilibili", lambda: "ok")

    record = next(
        item
        for item in caplog.records
        if item.getMessage().startswith("platform_request ")
    )
    assert record.platform == "bilibili"
    assert record.outcome == "success"
    assert record.error_code is None
    assert "https://" not in record.getMessage()
    assert "SESSDATA" not in record.getMessage()


def test_structured_log_marks_risk_and_circuit_open(caplog):
    limiter, _ = _limiter(
        PlatformPolicy(max_retries=0, circuit_threshold=1)
    )

    with caplog.at_level(
        logging.WARNING,
        logger="src.core.platforms.rate_limit",
    ):
        with pytest.raises(PlatformRequestError):
            limiter.execute("bilibili", lambda: (_ for _ in ()).throw(_status_error(412)))

    messages = [record.getMessage() for record in caplog.records]
    assert any("outcome=risk_control" in message for message in messages)
    assert any("platform_circuit_open" in message for message in messages)
