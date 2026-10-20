"""PlatformThrottle 的等待与限流测试。"""

from __future__ import annotations

import pytest

from src.core.discovery.models import DiscoveryError
from src.core.discovery.throttle import PlatformThrottle


def test_throttle_waits_between_requests():
    now = [0.0]
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    throttle = PlatformThrottle(
        {"fake": 1000},
        max_wait_seconds=2.0,
        clock=lambda: now[0],
        sleep=fake_sleep,
    )

    throttle.acquire("fake")
    now[0] += 0.2
    throttle.acquire("fake")

    assert sleeps == [pytest.approx(0.8)]
    assert now[0] == pytest.approx(1.0)


def test_throttle_without_interval_does_not_sleep():
    sleeps: list[float] = []
    throttle = PlatformThrottle(
        {"fake": 0},
        sleep=lambda seconds: sleeps.append(seconds),
    )

    throttle.acquire("fake")
    throttle.acquire("fake")

    assert sleeps == []


def test_throttle_raises_when_wait_exceeds_limit():
    now = [0.0]
    throttle = PlatformThrottle(
        {"fake": 1000},
        max_wait_seconds=0.1,
        clock=lambda: now[0],
        sleep=lambda seconds: None,
    )

    throttle.acquire("fake")
    now[0] += 0.2

    with pytest.raises(DiscoveryError) as exc_info:
        throttle.acquire("fake")

    assert exc_info.value.code == "rate_limited"
    assert exc_info.value.retry_after_seconds == 1
