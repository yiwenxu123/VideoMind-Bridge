"""进程内平台级节流。"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable

from .models import DiscoveryError


class PlatformThrottle:
    """串行化同一进程内的平台请求，超出等待上限时返回 rate_limited。"""

    def __init__(
        self,
        intervals_ms: dict[str, int],
        *,
        max_wait_seconds: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._intervals = {
            platform: max(0, interval) / 1000.0
            for platform, interval in intervals_ms.items()
        }
        self._max_wait_seconds = max_wait_seconds
        self._clock = clock
        self._sleep = sleep
        self._last_request: dict[str, float] = {}
        self._lock = threading.Lock()

    def acquire(self, platform: str) -> None:
        interval = self._intervals.get(platform, 0.0)
        if interval <= 0:
            return
        with self._lock:
            now = self._clock()
            last = self._last_request.get(platform)
            wait = 0.0 if last is None else interval - (now - last)
            if wait > self._max_wait_seconds:
                raise DiscoveryError(
                    "rate_limited",
                    f"{platform} 请求过于频繁",
                    retry_after_seconds=max(1, math.ceil(wait)),
                )
            if wait > 0:
                self._sleep(wait)
                now = self._clock()
            self._last_request[platform] = now
