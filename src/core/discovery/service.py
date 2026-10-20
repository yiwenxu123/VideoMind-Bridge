"""Discovery 编排：限额、成本、缓存、错误归一化。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from ..models import _COST_TIER_PRIORITY, CostTier
from .base import DiscoveryProvider
from .cache import TTLCache
from .config import (
    DEFAULT_COMMENTS_LIMIT,
    DEFAULT_CREATOR_FEED_LIMIT,
    DEFAULT_REPLIES_PER_THREAD,
    MAX_COMMENTS_LIMIT,
    MAX_CREATOR_FEED_LIMIT,
    MAX_REPLIES_PER_THREAD,
    comments_cache_ttl,
    creator_feed_cache_ttl,
    platform_min_intervals,
)
from .models import CommentsResult, CreatorFeedResult, DiscoveryError
from .registry import build_default_providers
from .throttle import PlatformThrottle

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class DiscoveryService:
    def __init__(
        self,
        providers: list[DiscoveryProvider] | None = None,
        cache: TTLCache | None = None,
        throttle: PlatformThrottle | None = None,
    ) -> None:
        self._providers = (
            list(providers) if providers is not None else build_default_providers()
        )
        self._cache = cache or TTLCache()
        self._throttle = throttle or PlatformThrottle(platform_min_intervals())

    def creator_feed(
        self,
        url: str,
        *,
        limit: int = DEFAULT_CREATOR_FEED_LIMIT,
        max_cost: CostTier | None = CostTier.CHEAP,
        request_id: str | None = None,
    ) -> CreatorFeedResult:
        request_id = request_id or uuid4().hex
        self._validate_url(url)
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise DiscoveryError("invalid_request", "limit 必须是整数")
        if limit < 1 or limit > MAX_CREATOR_FEED_LIMIT:
            raise DiscoveryError(
                "invalid_request",
                f"limit 必须在 1-{MAX_CREATOR_FEED_LIMIT} 之间",
            )

        provider = self._select_provider(url)
        if provider is None:
            return self._failure(
                request_id=request_id,
                platform="unknown",
                source="discovery",
                cost_tier=max_cost or CostTier.CHEAP,
                error_code="not_supported",
                error="只支持已接入平台的创作者主页",
            )

        if (
            max_cost is not None
            and _COST_TIER_PRIORITY.get(provider.cost_tier(), 99)
            > _COST_TIER_PRIORITY.get(max_cost, 99)
        ):
            return self._failure(
                request_id=request_id,
                platform=provider.platform,
                source=provider.source_name,
                cost_tier=provider.cost_tier(),
                error_code="cost_exceeded",
                error=(
                    f"provider 成本 {provider.cost_tier().value} "
                    f"超过 max_cost {max_cost.value}"
                ),
            )

        cache_key = self._cache_key(url, provider, limit, max_cost)
        cached = self._cache.get(cache_key)
        if isinstance(cached, CreatorFeedResult):
            cached.cached = True
            cached.request_id = request_id
            return cached

        try:
            self._throttle.acquire(provider.platform)
        except DiscoveryError as exc:
            return self._failure(
                request_id=request_id,
                platform=provider.platform,
                source=provider.source_name,
                cost_tier=provider.cost_tier(),
                error_code=exc.code,
                error=exc.message,
                retry_after_seconds=exc.retry_after_seconds,
            )

        try:
            result = provider.fetch_creator_feed(url, limit)
        except DiscoveryError as exc:
            return self._failure(
                request_id=request_id,
                platform=provider.platform,
                source=provider.source_name,
                cost_tier=provider.cost_tier(),
                error_code=exc.code,
                error=exc.message,
                retry_after_seconds=exc.retry_after_seconds,
            )
        except Exception:
            logger.exception("creator feed provider 异常: %s", provider.platform)
            return self._failure(
                request_id=request_id,
                platform=provider.platform,
                source=provider.source_name,
                cost_tier=provider.cost_tier(),
                error_code="internal_error",
                error="采集服务内部错误",
            )

        result.platform = provider.platform
        result.source = provider.source_name
        result.cost_tier = provider.cost_tier()
        result.request_id = request_id
        result.fetched_at = _now_iso()
        result.cached = False

        if result.success and result.completeness == "full":
            self._cache.set(cache_key, result, creator_feed_cache_ttl())
        return result

    def comments(
        self,
        url: str,
        *,
        limit: int = DEFAULT_COMMENTS_LIMIT,
        sort: str = "hot",
        include_replies: bool = False,
        max_replies_per_thread: int = DEFAULT_REPLIES_PER_THREAD,
        include_author: bool = False,
        max_cost: CostTier | None = CostTier.CHEAP,
        request_id: str | None = None,
    ) -> CommentsResult:
        request_id = request_id or uuid4().hex
        self._validate_url(url)
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise DiscoveryError("invalid_request", "limit 必须是整数")
        if limit < 1 or limit > MAX_COMMENTS_LIMIT:
            raise DiscoveryError(
                "invalid_request",
                f"limit 必须在 1-{MAX_COMMENTS_LIMIT} 之间",
            )
        if isinstance(max_replies_per_thread, bool) or not isinstance(
            max_replies_per_thread, int
        ):
            raise DiscoveryError("invalid_request", "max_replies_per_thread 必须是整数")
        if max_replies_per_thread < 1 or max_replies_per_thread > MAX_REPLIES_PER_THREAD:
            raise DiscoveryError(
                "invalid_request",
                f"max_replies_per_thread 必须在 1-{MAX_REPLIES_PER_THREAD} 之间",
            )
        normalized_sort = str(sort).strip().lower()
        if normalized_sort not in {"hot", "recent"}:
            raise DiscoveryError("invalid_request", "sort 必须是 hot 或 recent")

        provider = self._select_comments_provider(url)
        if provider is None:
            return self._comments_failure(
                request_id=request_id,
                platform="unknown",
                source="discovery",
                cost_tier=max_cost or CostTier.CHEAP,
                sort=normalized_sort,
                error_code="not_supported",
                error="只支持已接入平台的内容链接",
            )

        if (
            max_cost is not None
            and _COST_TIER_PRIORITY.get(provider.cost_tier(), 99)
            > _COST_TIER_PRIORITY.get(max_cost, 99)
        ):
            return self._comments_failure(
                request_id=request_id,
                platform=provider.platform,
                source=provider.source_name,
                cost_tier=provider.cost_tier(),
                sort=normalized_sort,
                error_code="cost_exceeded",
                error=(
                    f"provider 成本 {provider.cost_tier().value} "
                    f"超过 max_cost {max_cost.value}"
                ),
            )

        cache_key = self._comments_cache_key(
            url,
            provider,
            limit,
            normalized_sort,
            include_replies,
            max_replies_per_thread,
            include_author,
            max_cost,
        )
        cached = self._cache.get(cache_key)
        if isinstance(cached, CommentsResult):
            cached.cached = True
            cached.request_id = request_id
            return cached

        try:
            self._throttle.acquire(provider.platform)
        except DiscoveryError as exc:
            return self._comments_failure(
                request_id=request_id,
                platform=provider.platform,
                source=provider.source_name,
                cost_tier=provider.cost_tier(),
                sort=normalized_sort,
                error_code=exc.code,
                error=exc.message,
                retry_after_seconds=exc.retry_after_seconds,
            )

        try:
            result = provider.fetch_comments(
                url,
                limit=limit,
                sort=normalized_sort,
                include_replies=include_replies,
                max_replies_per_thread=max_replies_per_thread,
                include_author=include_author,
            )
        except DiscoveryError as exc:
            return self._comments_failure(
                request_id=request_id,
                platform=provider.platform,
                source=provider.source_name,
                cost_tier=provider.cost_tier(),
                sort=normalized_sort,
                error_code=exc.code,
                error=exc.message,
                retry_after_seconds=exc.retry_after_seconds,
            )
        except Exception:
            logger.exception("comments provider 异常: %s", provider.platform)
            return self._comments_failure(
                request_id=request_id,
                platform=provider.platform,
                source=provider.source_name,
                cost_tier=provider.cost_tier(),
                sort=normalized_sort,
                error_code="internal_error",
                error="采集服务内部错误",
            )

        result.platform = provider.platform
        result.source = provider.source_name
        result.cost_tier = provider.cost_tier()
        result.request_id = request_id
        result.fetched_at = _now_iso()
        result.cached = False
        result.sort = normalized_sort

        if result.success and result.completeness == "full":
            self._cache.set(cache_key, result, comments_cache_ttl())
        return result

    def _select_provider(self, url: str) -> DiscoveryProvider | None:
        candidates = [
            provider for provider in self._providers
            if provider.supports_creator_url(url)
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda provider: _COST_TIER_PRIORITY.get(provider.cost_tier(), 99),
        )

    def _select_comments_provider(self, url: str) -> DiscoveryProvider | None:
        candidates = [
            provider for provider in self._providers
            if provider.supports_comments(url)
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda provider: _COST_TIER_PRIORITY.get(provider.cost_tier(), 99),
        )

    @staticmethod
    def _validate_url(url: str) -> None:
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise DiscoveryError("invalid_request", "url 格式非法") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise DiscoveryError("invalid_request", "url 必须是 http/https 链接")

    @staticmethod
    def _cache_key(
        url: str,
        provider: DiscoveryProvider,
        limit: int,
        max_cost: CostTier | None,
    ) -> str:
        parsed = urlsplit(url)
        canonical = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, "", "")
        )
        max_cost_value = max_cost.value if max_cost is not None else "none"
        return (
            f"creator_feed:{provider.platform}:{canonical}:"
            f"{limit}:{max_cost_value}"
        )

    @staticmethod
    def _comments_cache_key(
        url: str,
        provider: DiscoveryProvider,
        limit: int,
        sort: str,
        include_replies: bool,
        max_replies_per_thread: int,
        include_author: bool,
        max_cost: CostTier | None,
    ) -> str:
        parsed = urlsplit(url)
        canonical = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, "", "")
        )
        max_cost_value = max_cost.value if max_cost is not None else "none"
        return (
            f"comments:{provider.platform}:{canonical}:{limit}:{sort}:"
            f"{int(include_replies)}:{max_replies_per_thread}:"
            f"{int(include_author)}:{max_cost_value}"
        )

    @staticmethod
    def _failure(
        *,
        request_id: str,
        platform: str,
        source: str,
        cost_tier: CostTier,
        error_code: str,
        error: str,
        retry_after_seconds: int | None = None,
    ) -> CreatorFeedResult:
        return CreatorFeedResult(
            success=False,
            platform=platform,
            source=source,
            cost_tier=cost_tier,
            completeness="none",
            request_id=request_id,
            fetched_at=_now_iso(),
            error=error,
            error_code=error_code,
            retry_after_seconds=retry_after_seconds,
        )

    @staticmethod
    def _comments_failure(
        *,
        request_id: str,
        platform: str,
        source: str,
        cost_tier: CostTier,
        sort: str,
        error_code: str,
        error: str,
        retry_after_seconds: int | None = None,
    ) -> CommentsResult:
        return CommentsResult(
            success=False,
            platform=platform,
            source=source,
            cost_tier=cost_tier,
            completeness="none",
            sort=sort,
            request_id=request_id,
            fetched_at=_now_iso(),
            error=error,
            error_code=error_code,
            retry_after_seconds=retry_after_seconds,
        )
