"""进程内 TTL LRU 缓存。"""

from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class TTLCache:
    def __init__(
        self,
        max_entries: int = 256,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= self._clock():
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return copy.deepcopy(entry.value)

    def set(self, key: str, value: Any, ttl: float) -> None:
        if ttl <= 0:
            return
        with self._lock:
            self._entries[key] = _CacheEntry(
                value=copy.deepcopy(value),
                expires_at=self._clock() + ttl,
            )
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
