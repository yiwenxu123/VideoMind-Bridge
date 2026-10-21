"""平台级请求节流、退避与熔断。"""

from __future__ import annotations

import json
import math
import os
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

_RISK_STATUS = {403, 412}
_NO_RETRY_STATUS = {400, 401, 403, 404, 412}
_DEFAULT_INTERVALS = {
    "bilibili": 1000,
    "douyin": 2000,
    "xiaohongshu": 1500,
    "youtube": 500,
}


@dataclass(frozen=True)
class PlatformPolicy:
    min_interval_ms: int = 0
    max_concurrency: int = 1
    max_retries: int = 2
    backoff_base_ms: int = 500
    backoff_max_ms: int = 4000
    max_wait_seconds: float = 2.0
    circuit_threshold: int = 3
    circuit_cooldown_seconds: float = 60.0


class PlatformRequestError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _intervals_from_env() -> dict[str, int]:
    raw = os.getenv("VMB_PLATFORM_INTERVALS_MS", "")
    data: Any = _DEFAULT_INTERVALS
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = _DEFAULT_INTERVALS
    if not isinstance(data, dict):
        data = _DEFAULT_INTERVALS
    intervals: dict[str, int] = {}
    for platform, value in data.items():
        try:
            intervals[str(platform)] = max(0, int(value))
        except (TypeError, ValueError):
            continue
    return intervals


class PlatformRateLimiter:
    def __init__(
        self,
        policies: dict[str, PlatformPolicy] | None = None,
        *,
        enabled: bool = True,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self.enabled = enabled
        self._policies = policies or {}
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._lock = threading.RLock()
        self._semaphores: dict[str, threading.BoundedSemaphore] = {}
        self._last_request: dict[str, float] = {}
        self._failures: dict[str, int] = {}
        self._circuit_until: dict[str, float] = {}

    @classmethod
    def from_env(cls) -> PlatformRateLimiter:
        intervals = _intervals_from_env()
        explicit_max_wait = _env_float("VMB_PLATFORM_MAX_WAIT_SECONDS", 0.0)
        has_explicit_max_wait = "VMB_PLATFORM_MAX_WAIT_SECONDS" in os.environ
        policies = {
            platform: PlatformPolicy(
                min_interval_ms=interval,
                max_concurrency=max(1, _env_int("VMB_PLATFORM_MAX_CONCURRENCY", 1)),
                max_retries=_env_int("VMB_PLATFORM_MAX_RETRIES", 2),
                backoff_base_ms=_env_int("VMB_PLATFORM_BACKOFF_BASE_MS", 500),
                backoff_max_ms=_env_int("VMB_PLATFORM_BACKOFF_MAX_MS", 4000),
                max_wait_seconds=(
                    explicit_max_wait
                    if has_explicit_max_wait
                    else max(2.0, interval / 1000.0 + 1.0)
                ),
                circuit_threshold=max(
                    1,
                    _env_int("VMB_PLATFORM_CIRCUIT_THRESHOLD", 3),
                ),
                circuit_cooldown_seconds=_env_float(
                    "VMB_PLATFORM_CIRCUIT_COOLDOWN_SEC",
                    60.0,
                ),
            )
            for platform, interval in intervals.items()
        }
        return cls(
            policies,
            enabled=_env_bool("VMB_PLATFORM_RATE_LIMIT_ENABLED", True),
        )

    def _policy(self, platform: str) -> PlatformPolicy:
        return self._policies.get(
            platform,
            PlatformPolicy(
                max_concurrency=1,
                max_retries=2,
                backoff_base_ms=500,
                backoff_max_ms=4000,
            ),
        )

    def _semaphore(self, platform: str, policy: PlatformPolicy) -> threading.BoundedSemaphore:
        with self._lock:
            sem = self._semaphores.get(platform)
            if sem is None:
                sem = threading.BoundedSemaphore(max(1, policy.max_concurrency))
                self._semaphores[platform] = sem
            return sem

    def _check_circuit(self, platform: str) -> None:
        now = self._clock()
        with self._lock:
            until = self._circuit_until.get(platform, 0.0)
            if until > now:
                raise PlatformRequestError(
                    "risk_control",
                    f"{platform} 熔断中，请稍后重试",
                    retry_after_seconds=max(1, math.ceil(until - now)),
                )
            if until:
                self._circuit_until.pop(platform, None)
                self._failures[platform] = 0

    def _pace(self, platform: str, policy: PlatformPolicy, deadline: float | None) -> None:
        if policy.min_interval_ms <= 0:
            return
        interval = policy.min_interval_ms / 1000.0
        with self._lock:
            now = self._clock()
            last = self._last_request.get(platform)
            slot = max(now, (last + interval) if last is not None else now)
            self._last_request[platform] = slot
        wait = slot - now
        if wait <= 0:
            return
        if wait > policy.max_wait_seconds:
            raise PlatformRequestError(
                "rate_limited",
                f"{platform} 请求过于频繁",
                retry_after_seconds=max(1, math.ceil(wait)),
            )
        if deadline is not None and self._clock() + wait > deadline:
            raise PlatformRequestError(
                "rate_limited",
                f"{platform} 等待将超过总超时",
                retry_after_seconds=max(1, math.ceil(wait)),
            )
        self._sleep(wait)

    def _backoff(self, attempt: int, policy: PlatformPolicy) -> float:
        base = policy.backoff_base_ms / 1000.0
        delay = min(policy.backoff_max_ms / 1000.0, base * (2**attempt))
        return float(delay + self._rng.uniform(0, 0.25))

    def _sleep_with_deadline(
        self,
        seconds: float,
        deadline: float | None,
        platform: str,
    ) -> None:
        if deadline is not None and self._clock() + seconds > deadline:
            raise PlatformRequestError(
                "rate_limited",
                f"{platform} 重试将超过总超时",
                retry_after_seconds=max(1, math.ceil(seconds)),
            )
        if seconds > 0:
            self._sleep(seconds)

    def _record_success(self, platform: str) -> None:
        with self._lock:
            self._failures[platform] = 0
            self._circuit_until.pop(platform, None)

    def _record_failure(self, platform: str, policy: PlatformPolicy) -> None:
        with self._lock:
            failures = self._failures.get(platform, 0) + 1
            self._failures[platform] = failures
            if failures >= policy.circuit_threshold:
                self._circuit_until[platform] = (
                    self._clock() + policy.circuit_cooldown_seconds
                )

    def notify_risk_control(self, platform: str) -> None:
        """登记 HTTP 200 响应体里的风控信号，让后续请求走熔断。"""
        if not self.enabled:
            return
        self._record_failure(platform, self._policy(platform))

    def circuit_state(self, platform: str) -> str:
        with self._lock:
            return (
                "open"
                if self._circuit_until.get(platform, 0.0) > self._clock()
                else "closed"
            )

    def execute(
        self,
        platform: str,
        func: Callable[[], Any],
        *,
        deadline: float | None = None,
    ) -> Any:
        if not self.enabled:
            return func()

        policy = self._policy(platform)
        self._check_circuit(platform)
        semaphore = self._semaphore(platform, policy)
        timeout = None
        if deadline is not None:
            timeout = max(0.0, deadline - self._clock())
        if not semaphore.acquire(timeout=timeout):
            raise PlatformRequestError(
                "rate_limited",
                f"{platform} 并发已满",
                retry_after_seconds=1,
            )

        try:
            for attempt in range(policy.max_retries + 1):
                self._pace(platform, policy, deadline)
                try:
                    result = func()
                    self._record_success(platform)
                    return result
                except PlatformRequestError:
                    raise
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    if status == 401:
                        raise PlatformRequestError(
                            "auth_required",
                            f"{platform} 需要登录态",
                            status_code=status,
                        ) from exc
                    if status in _RISK_STATUS:
                        self._record_failure(platform, policy)
                        raise PlatformRequestError(
                            "risk_control",
                            f"{platform} 触发风控",
                            status_code=status,
                            retry_after_seconds=60,
                        ) from exc
                    if status == 429:
                        retry_after = self._retry_after(exc.response)
                        if attempt < policy.max_retries:
                            self._sleep_with_deadline(
                                retry_after
                                if retry_after is not None
                                else self._backoff(attempt, policy),
                                deadline,
                                platform,
                            )
                            continue
                        raise PlatformRequestError(
                            "rate_limited",
                            f"{platform} 限流",
                            status_code=status,
                            retry_after_seconds=retry_after or 60,
                        ) from exc
                    if status in _NO_RETRY_STATUS:
                        raise PlatformRequestError(
                            "not_found" if status == 404 else "upstream_error",
                            f"{platform} HTTP {status}",
                            status_code=status,
                        ) from exc
                    if status >= 500 and attempt < policy.max_retries:
                        self._sleep_with_deadline(
                            self._backoff(attempt, policy),
                            deadline,
                            platform,
                        )
                        continue
                    raise PlatformRequestError(
                        "upstream_error",
                        f"{platform} HTTP {status}",
                        status_code=status,
                    ) from exc
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    if attempt < policy.max_retries:
                        self._sleep_with_deadline(
                            self._backoff(attempt, policy),
                            deadline,
                            platform,
                        )
                        continue
                    raise PlatformRequestError(
                        "upstream_error",
                        f"{platform} 请求超时/网络错误",
                    ) from exc
            raise PlatformRequestError("upstream_error", f"{platform} 请求失败")
        finally:
            semaphore.release()

    @staticmethod
    def _retry_after(response: httpx.Response) -> int | None:
        raw = response.headers.get("Retry-After", "").strip()
        if not raw:
            return None
        try:
            return max(1, int(raw))
        except ValueError:
            return None


_limiter: PlatformRateLimiter | None = None
_limiter_lock = threading.Lock()


def get_platform_rate_limiter() -> PlatformRateLimiter:
    global _limiter
    with _limiter_lock:
        if _limiter is None:
            _limiter = PlatformRateLimiter.from_env()
        return _limiter


def reset_platform_rate_limiter() -> None:
    global _limiter
    with _limiter_lock:
        _limiter = None
