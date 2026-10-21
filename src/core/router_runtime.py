"""长生命周期 Router 运行时：缓存、成本透传与资源关闭。"""

from __future__ import annotations

import logging
import os
import threading
import time

from .cache import TTLCache
from .models import CostTier, ExtractOptions, ExtractResult
from .router import ContentRouter, RouterConfig

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_TTL = 600
_DEFAULT_CACHE_MAX_ENTRIES = 256
_EXTRACTOR_STATUS_TTL = 60


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


class RouterRuntime:
    """进程级 Router 运行时。

    - 缓存跨请求复用，key 包含成本与 ASR 选项；
    - 只缓存 full 成功结果，避免 meta/失败挡住更高成本路径；
    - 负责关闭 Router 及其已实例化提取器。
    """

    def __init__(
        self,
        router: ContentRouter | None = None,
        cache: TTLCache | None = None,
        cache_ttl: int | None = None,
    ) -> None:
        if router is None:
            # 延迟从包入口取，保留 src.core.ContentRouter 的 mock/注入能力
            from . import ContentRouter as CoreContentRouter
            router = CoreContentRouter(RouterConfig(use_cache=False))
        self._router = router
        self._cache = cache or TTLCache(
            max_entries=_env_int(
                "VMB_EXTRACT_CACHE_MAX_ENTRIES",
                _DEFAULT_CACHE_MAX_ENTRIES,
            )
        )
        self._cache_ttl = (
            cache_ttl
            if cache_ttl is not None
            else _env_int("VMB_EXTRACT_CACHE_TTL", _DEFAULT_CACHE_TTL)
        )
        self._status_lock = threading.Lock()
        self._status_cache: tuple[float, dict[str, bool]] | None = None

    @property
    def router(self) -> ContentRouter:
        return self._router

    def extract(
        self,
        url: str,
        *,
        max_cost: CostTier | None = None,
        options: ExtractOptions | None = None,
    ) -> ExtractResult:
        key = self._cache_key(url, max_cost, options)
        cached = self._cache.get(key)
        if isinstance(cached, ExtractResult):
            if options and options.request_id:
                cached.request_id = options.request_id
            return cached

        if options is not None:
            result = self._router.extract(url, max_cost=max_cost, options=options)
        else:
            result = self._router.extract(url, max_cost=max_cost)
        if (
            result.success
            and result.completeness == "full"
            and result.content.strip()
            and not result.is_placeholder
        ):
            self._cache.set(key, result, self._cache_ttl)
        return result

    def extractor_status(self) -> dict[str, bool]:
        now = time.monotonic()
        with self._status_lock:
            if self._status_cache and now - self._status_cache[0] < _EXTRACTOR_STATUS_TTL:
                return dict(self._status_cache[1])
            status = self._router.list_extractors()
            self._status_cache = (now, status)
            return dict(status)

    def close(self) -> None:
        self._cache.clear()
        with self._status_lock:
            self._status_cache = None
        self._router.close()
        logger.info("RouterRuntime 已关闭")

    @staticmethod
    def _cache_key(
        url: str,
        max_cost: CostTier | None,
        options: ExtractOptions | None,
    ) -> str:
        canonical_url = url.split("#", 1)[0]
        chain = ",".join(options.asr_chain or []) if options else ""
        language = (options.asr_language or "") if options else ""
        asr_max_cost = (
            options.asr_max_cost.value
            if options and options.asr_max_cost is not None
            else ""
        )
        max_cost_value = max_cost.value if max_cost is not None else ""
        return (
            f"extract:{canonical_url}|{max_cost_value}|"
            f"{chain}|{language}|{asr_max_cost}"
        )
