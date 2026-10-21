"""平台级请求节流、退避与熔断。"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

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


@dataclass
class PlatformMetrics:
    requests_total: int = 0
    success_total: int = 0
    failure_total: int = 0
    retries_total: int = 0
    risk_control_total: int = 0
    risk_control_signals_total: int = 0
    rate_limited_total: int = 0
    upstream_error_total: int = 0
    auth_required_total: int = 0
    not_found_total: int = 0
    client_error_total: int = 0
    circuit_open_total: int = 0
    circuit_rejected_total: int = 0
    latency_ms_total: float = 0.0
    latency_ms_max: float = 0.0

    def to_dict(self) -> dict[str, float | int]:
        average = (
            self.latency_ms_total / self.requests_total
            if self.requests_total
            else 0.0
        )
        return {
            "requests_total": self.requests_total,
            "success_total": self.success_total,
            "failure_total": self.failure_total,
            "retries_total": self.retries_total,
            "risk_control_total": self.risk_control_total,
            "risk_control_signals_total": self.risk_control_signals_total,
            "rate_limited_total": self.rate_limited_total,
            "upstream_error_total": self.upstream_error_total,
            "auth_required_total": self.auth_required_total,
            "not_found_total": self.not_found_total,
            "client_error_total": self.client_error_total,
            "circuit_open_total": self.circuit_open_total,
            "circuit_rejected_total": self.circuit_rejected_total,
            "latency_ms_avg": round(average, 2),
            "latency_ms_max": round(self.latency_ms_max, 2),
        }


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
        self._metrics: dict[str, PlatformMetrics] = {
            platform: PlatformMetrics() for platform in self._policies
        }

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
        retry_after: int | None = None
        with self._lock:
            until = self._circuit_until.get(platform, 0.0)
            if until > now:
                self._metrics_locked(platform).circuit_rejected_total += 1
                retry_after = max(1, math.ceil(until - now))
            elif until:
                self._circuit_until.pop(platform, None)
                self._failures[platform] = 0
        if retry_after is not None:
            logger.warning(
                "platform_circuit_rejected platform=%s retry_after_s=%s",
                platform,
                retry_after,
                extra={
                    "platform": platform,
                    "retry_after_seconds": retry_after,
                },
            )
            raise PlatformRequestError(
                "risk_control",
                f"{platform} 熔断中，请稍后重试",
                retry_after_seconds=retry_after,
            )

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

    def _metrics_locked(self, platform: str) -> PlatformMetrics:
        metrics = self._metrics.get(platform)
        if metrics is None:
            metrics = PlatformMetrics()
            self._metrics[platform] = metrics
        return metrics

    def _elapsed_ms(self, started: float) -> float:
        return max(0.0, (self._clock() - started) * 1000.0)

    def _record_retry(self, platform: str) -> None:
        with self._lock:
            self._metrics_locked(platform).retries_total += 1

    def _record_outcome(
        self,
        platform: str,
        *,
        success: bool,
        latency_ms: float,
        error_code: str | None = None,
    ) -> None:
        with self._lock:
            metrics = self._metrics_locked(platform)
            metrics.requests_total += 1
            if success:
                metrics.success_total += 1
            else:
                metrics.failure_total += 1
                field = {
                    "risk_control": "risk_control_total",
                    "rate_limited": "rate_limited_total",
                    "upstream_error": "upstream_error_total",
                    "auth_required": "auth_required_total",
                    "not_found": "not_found_total",
                    "client_error": "client_error_total",
                }.get(error_code or "")
                if field:
                    setattr(metrics, field, getattr(metrics, field) + 1)
            metrics.latency_ms_total += latency_ms
            metrics.latency_ms_max = max(metrics.latency_ms_max, latency_ms)

    def _log_outcome(
        self,
        platform: str,
        *,
        success: bool,
        latency_ms: float,
        retries: int,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        outcome = "success" if success else (error_code or "error")
        extra = {
            "platform": platform,
            "outcome": outcome,
            "status_code": status_code,
            "latency_ms": round(latency_ms, 2),
            "retries": retries,
            "error_code": error_code,
        }
        if success:
            logger.info(
                "platform_request platform=%s outcome=success status=%s latency_ms=%.2f retries=%s",
                platform,
                status_code,
                latency_ms,
                retries,
                extra=extra,
            )
        else:
            logger.warning(
                "platform_request platform=%s outcome=%s status=%s latency_ms=%.2f retries=%s",
                platform,
                outcome,
                status_code,
                latency_ms,
                retries,
                extra=extra,
            )

    def _log_retry(
        self,
        platform: str,
        attempt: int,
        error_code: str,
        retry_after_seconds: int | None,
    ) -> None:
        logger.warning(
            "platform_request_retry platform=%s attempt=%s error_code=%s retry_after_s=%s",
            platform,
            attempt,
            error_code,
            retry_after_seconds,
            extra={
                "platform": platform,
                "attempt": attempt,
                "error_code": error_code,
                "retry_after_seconds": retry_after_seconds,
            },
        )

    def _log_circuit_open(
        self,
        platform: str,
        failures: int,
        cooldown_seconds: float,
    ) -> None:
        logger.warning(
            "platform_circuit_open platform=%s failures=%s cooldown_s=%s",
            platform,
            failures,
            cooldown_seconds,
            extra={
                "platform": platform,
                "failures": failures,
                "cooldown_seconds": cooldown_seconds,
            },
        )

    def _record_success(self, platform: str) -> None:
        with self._lock:
            self._failures[platform] = 0
            self._circuit_until.pop(platform, None)

    def _record_failure(
        self,
        platform: str,
        policy: PlatformPolicy,
    ) -> tuple[bool, int]:
        with self._lock:
            failures = self._failures.get(platform, 0) + 1
            self._failures[platform] = failures
            if failures >= policy.circuit_threshold:
                self._circuit_until[platform] = (
                    self._clock() + policy.circuit_cooldown_seconds
                )
                self._metrics_locked(platform).circuit_open_total += 1
                return True, failures
        return False, failures

    def notify_risk_control(self, platform: str) -> None:
        """登记 HTTP 200 响应体里的风控信号，让后续请求走熔断。"""
        if not self.enabled:
            return
        policy = self._policy(platform)
        opened, failures = self._record_failure(platform, policy)
        with self._lock:
            self._metrics_locked(platform).risk_control_signals_total += 1
        logger.warning(
            "platform_risk_signal platform=%s failures=%s",
            platform,
            failures,
            extra={"platform": platform, "failures": failures},
        )
        if opened:
            self._log_circuit_open(
                platform,
                failures,
                policy.circuit_cooldown_seconds,
            )

    def circuit_state(self, platform: str) -> str:
        with self._lock:
            return (
                "open"
                if self._circuit_until.get(platform, 0.0) > self._clock()
                else "closed"
            )

    def metrics_snapshot(self) -> dict[str, dict[str, Any]]:
        """返回进程内平台请求计数与熔断状态（重启清零）。"""
        with self._lock:
            now = self._clock()
            return {
                platform: {
                    **metrics.to_dict(),
                    "circuit": (
                        "open"
                        if self._circuit_until.get(platform, 0.0) > now
                        else "closed"
                    ),
                }
                for platform, metrics in self._metrics.items()
            }

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
        started = self._clock()
        retries = 0
        if not semaphore.acquire(timeout=timeout):
            latency_ms = self._elapsed_ms(started)
            error = PlatformRequestError(
                "rate_limited",
                f"{platform} 并发已满",
                retry_after_seconds=1,
            )
            self._record_outcome(
                platform,
                success=False,
                latency_ms=latency_ms,
                error_code=error.code,
            )
            self._log_outcome(
                platform,
                success=False,
                latency_ms=latency_ms,
                retries=0,
                error_code=error.code,
            )
            raise error

        try:
            try:
                for attempt in range(policy.max_retries + 1):
                    self._pace(platform, policy, deadline)
                    try:
                        result = func()
                        self._record_success(platform)
                        latency_ms = self._elapsed_ms(started)
                        self._record_outcome(
                            platform,
                            success=True,
                            latency_ms=latency_ms,
                        )
                        self._log_outcome(
                            platform,
                            success=True,
                            latency_ms=latency_ms,
                            retries=retries,
                            status_code=getattr(result, "status_code", None),
                        )
                        return result
                    except httpx.HTTPStatusError as exc:
                        status = exc.response.status_code
                        if status == 401:
                            raise PlatformRequestError(
                                "auth_required",
                                f"{platform} 需要登录态",
                                status_code=status,
                            ) from exc
                        if status in _RISK_STATUS:
                            opened, failures = self._record_failure(platform, policy)
                            if opened:
                                self._log_circuit_open(
                                    platform,
                                    failures,
                                    policy.circuit_cooldown_seconds,
                                )
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
                                retries += 1
                                self._record_retry(platform)
                                self._log_retry(
                                    platform,
                                    attempt + 1,
                                    "rate_limited",
                                    retry_after,
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
                            retries += 1
                            self._record_retry(platform)
                            self._log_retry(
                                platform,
                                attempt + 1,
                                "upstream_error",
                                None,
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
                            retries += 1
                            self._record_retry(platform)
                            self._log_retry(
                                platform,
                                attempt + 1,
                                "upstream_error",
                                None,
                            )
                            continue
                        raise PlatformRequestError(
                            "upstream_error",
                            f"{platform} 请求超时/网络错误",
                        ) from exc
                raise PlatformRequestError("upstream_error", f"{platform} 请求失败")
            except PlatformRequestError as exc:
                latency_ms = self._elapsed_ms(started)
                self._record_outcome(
                    platform,
                    success=False,
                    latency_ms=latency_ms,
                    error_code=exc.code,
                )
                self._log_outcome(
                    platform,
                    success=False,
                    latency_ms=latency_ms,
                    retries=retries,
                    status_code=exc.status_code,
                    error_code=exc.code,
                )
                raise
            except Exception as exc:
                latency_ms = self._elapsed_ms(started)
                error_code = getattr(exc, "error_code", None) or "client_error"
                status_code = getattr(exc, "status_code", None)
                self._record_outcome(
                    platform,
                    success=False,
                    latency_ms=latency_ms,
                    error_code=error_code,
                )
                self._log_outcome(
                    platform,
                    success=False,
                    latency_ms=latency_ms,
                    retries=retries,
                    status_code=status_code,
                    error_code=error_code,
                )
                raise
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
