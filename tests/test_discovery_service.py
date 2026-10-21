"""DiscoveryService 的限额、成本、缓存与错误映射测试。"""

from __future__ import annotations

import pytest

from src.core.discovery.base import DiscoveryProvider
from src.core.discovery.cache import TTLCache
from src.core.discovery.models import (
    CommentItem,
    CommentsResult,
    CreatorFeedItem,
    CreatorFeedResult,
    CreatorRef,
    DiscoveryError,
)
from src.core.discovery.service import DiscoveryService
from src.core.models import CostTier


class FakeProvider(DiscoveryProvider):
    platform = "fake"
    source_name = "fake_discovery"

    def __init__(
        self,
        *,
        cost: CostTier = CostTier.FREE,
        error: Exception | None = None,
        result: CreatorFeedResult | None = None,
    ) -> None:
        self._cost_tier = cost
        self.error = error
        self.result = result
        self.calls = 0

    def supports_creator_url(self, url: str) -> bool:
        return url.startswith("https://creator.example/")

    def fetch_creator_feed(self, url: str, limit: int) -> CreatorFeedResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return self.result
        return CreatorFeedResult(
            success=True,
            platform=self.platform,
            source=self.source_name,
            cost_tier=self._cost_tier,
            creator=CreatorRef(
                id="creator-1",
                name="示例创作者",
                url="https://creator.example/creator-1",
            ),
            items=[
                CreatorFeedItem(
                    id="video-1",
                    url="https://creator.example/video-1",
                    title="示例作品",
                    metrics={"views": 100, "likes": 10},
                )
            ],
            completeness="full",
            has_more=False,
        )


class FakeCommentsProvider(DiscoveryProvider):
    platform = "fake_comments"
    source_name = "fake_comments_discovery"

    def __init__(
        self,
        *,
        cost: CostTier = CostTier.FREE,
        error: Exception | None = None,
    ) -> None:
        self._cost_tier = cost
        self.error = error
        self.calls = 0
        self.last_kwargs: dict[str, object] = {}

    def supports_creator_url(self, url: str) -> bool:
        return False

    def fetch_creator_feed(self, url: str, limit: int) -> CreatorFeedResult:
        raise NotImplementedError

    def supports_comments(self, url: str) -> bool:
        return url.startswith("https://video.example/")

    def fetch_comments(
        self,
        url: str,
        *,
        limit: int,
        sort: str,
        include_replies: bool,
        max_replies_per_thread: int,
        include_author: bool,
    ) -> CommentsResult:
        self.calls += 1
        self.last_kwargs = {
            "limit": limit,
            "sort": sort,
            "include_replies": include_replies,
            "max_replies_per_thread": max_replies_per_thread,
            "include_author": include_author,
        }
        if self.error is not None:
            raise self.error
        return CommentsResult(
            success=True,
            platform=self.platform,
            source=self.source_name,
            cost_tier=self._cost_tier,
            items=[
                CommentItem(
                    id="comment-1",
                    parent_id=None,
                    root_id="comment-1",
                    text="示例评论",
                    likes=10,
                    is_reply=False,
                )
            ],
            completeness="full",
            sort=sort,
            has_more=False,
        )


def _service(provider: FakeProvider, cache: TTLCache | None = None) -> DiscoveryService:
    return DiscoveryService(providers=[provider], cache=cache)


def test_creator_feed_success_fills_common_fields(monkeypatch):
    monkeypatch.setenv("VMB_CREATOR_FEED_CACHE_TTL", "300")
    provider = FakeProvider()
    service = _service(provider)

    result = service.creator_feed(
        "https://creator.example/creator-1",
        limit=5,
        request_id="req-1",
    )

    assert result.success is True
    assert result.request_id == "req-1"
    assert result.platform == "fake"
    assert result.source == "fake_discovery"
    assert result.cost_tier == CostTier.FREE
    assert result.completeness == "full"
    assert result.cached is False
    assert result.fetched_at
    assert len(result.items) == 1
    assert provider.calls == 1

    payload = result.to_dict()
    assert payload["returned_count"] == 1
    assert payload["creator"]["id"] == "creator-1"
    assert payload["schema_version"] == "1.0"


def test_creator_feed_uses_cache_and_updates_request_id(monkeypatch):
    monkeypatch.setenv("VMB_CREATOR_FEED_CACHE_TTL", "300")
    provider = FakeProvider()
    service = _service(provider, TTLCache(max_entries=10))

    first = service.creator_feed(
        "https://creator.example/creator-1",
        limit=5,
        request_id="req-1",
    )
    second = service.creator_feed(
        "https://creator.example/creator-1",
        limit=5,
        request_id="req-2",
    )

    assert provider.calls == 1
    assert first.cached is False
    assert second.cached is True
    assert second.request_id == "req-2"
    assert second.creator is not None


def test_creator_feed_cache_key_includes_limit(monkeypatch):
    monkeypatch.setenv("VMB_CREATOR_FEED_CACHE_TTL", "300")
    provider = FakeProvider()
    service = _service(provider, TTLCache(max_entries=10))

    service.creator_feed("https://creator.example/creator-1", limit=5)
    service.creator_feed("https://creator.example/creator-1", limit=10)

    assert provider.calls == 2


def test_creator_feed_does_not_cache_partial_results(monkeypatch):
    monkeypatch.setenv("VMB_CREATOR_FEED_CACHE_TTL", "300")
    partial = CreatorFeedResult(
        success=True,
        platform="fake",
        source="fake_discovery",
        cost_tier=CostTier.FREE,
        completeness="partial",
    )
    provider = FakeProvider(result=partial)
    service = _service(provider, TTLCache(max_entries=10))

    service.creator_feed("https://creator.example/creator-1")
    service.creator_feed("https://creator.example/creator-1")

    assert provider.calls == 2


def test_creator_feed_unsupported_url_returns_failure():
    provider = FakeProvider()
    service = _service(provider)

    result = service.creator_feed("https://other.example/creator-1")

    assert result.success is False
    assert result.error_code == "not_supported"
    assert provider.calls == 0


def test_creator_feed_cost_exceeded_returns_failure():
    provider = FakeProvider(cost=CostTier.PAID)
    service = _service(provider)

    result = service.creator_feed(
        "https://creator.example/creator-1",
        max_cost=CostTier.CHEAP,
    )

    assert result.success is False
    assert result.error_code == "cost_exceeded"
    assert result.cost_tier == CostTier.PAID
    assert provider.calls == 0


def test_creator_feed_provider_error_maps_to_result():
    provider = FakeProvider(
        error=DiscoveryError(
            "risk_control",
            "B站风控",
            retry_after_seconds=60,
        )
    )
    service = _service(provider)

    result = service.creator_feed("https://creator.example/creator-1")

    assert result.success is False
    assert result.error_code == "risk_control"
    assert result.retry_after_seconds == 60
    assert result.error == "B站风控"


def test_creator_feed_generic_provider_error_maps_to_internal_error():
    provider = FakeProvider(error=RuntimeError("boom"))
    service = _service(provider)

    result = service.creator_feed("https://creator.example/creator-1")

    assert result.success is False
    assert result.error_code == "internal_error"


def test_creator_feed_invalid_url_raises():
    service = _service(FakeProvider())

    with pytest.raises(DiscoveryError) as exc_info:
        service.creator_feed("not-a-url")

    assert exc_info.value.code == "invalid_request"


@pytest.mark.parametrize("limit", [0, 31, "5", True])
def test_creator_feed_invalid_limit_raises(limit):
    service = _service(FakeProvider())

    with pytest.raises(DiscoveryError) as exc_info:
        service.creator_feed("https://creator.example/creator-1", limit=limit)

    assert exc_info.value.code == "invalid_request"


def test_comments_success_fills_common_fields(monkeypatch):
    monkeypatch.setenv("VMB_COMMENTS_CACHE_TTL", "300")
    provider = FakeCommentsProvider()
    service = DiscoveryService(providers=[provider], cache=TTLCache())

    result = service.comments(
        "https://video.example/video-1",
        limit=10,
        sort="recent",
        include_replies=True,
        max_replies_per_thread=2,
        include_author=True,
        request_id="req-c1",
    )

    assert result.success is True
    assert result.request_id == "req-c1"
    assert result.platform == "fake_comments"
    assert result.source == "fake_comments_discovery"
    assert result.sort == "recent"
    assert result.completeness == "full"
    assert result.cached is False
    assert result.fetched_at
    assert provider.calls == 1
    assert provider.last_kwargs == {
        "limit": 10,
        "sort": "recent",
        "include_replies": True,
        "max_replies_per_thread": 2,
        "include_author": True,
    }

    payload = result.to_dict()
    assert payload["returned_count"] == 1
    assert payload["top_level_count"] == 1
    assert payload["reply_count"] == 0


def test_comments_uses_cache_and_updates_request_id(monkeypatch):
    monkeypatch.setenv("VMB_COMMENTS_CACHE_TTL", "300")
    provider = FakeCommentsProvider()
    service = DiscoveryService(providers=[provider], cache=TTLCache())

    first = service.comments(
        "https://video.example/video-1",
        limit=10,
        request_id="req-1",
    )
    second = service.comments(
        "https://video.example/video-1",
        limit=10,
        request_id="req-2",
    )

    assert provider.calls == 1
    assert first.cached is False
    assert second.cached is True
    assert second.request_id == "req-2"


def test_comments_unsupported_url_returns_failure():
    provider = FakeCommentsProvider()
    service = DiscoveryService(providers=[provider], cache=TTLCache())

    result = service.comments("https://other.example/video-1")

    assert result.success is False
    assert result.error_code == "not_supported"


def test_comments_cost_exceeded_returns_failure():
    provider = FakeCommentsProvider(cost=CostTier.PAID)
    service = DiscoveryService(providers=[provider], cache=TTLCache())

    result = service.comments(
        "https://video.example/video-1",
        max_cost=CostTier.CHEAP,
    )

    assert result.success is False
    assert result.error_code == "cost_exceeded"


def test_comments_provider_error_maps_to_result():
    provider = FakeCommentsProvider(
        error=DiscoveryError("risk_control", "B站风控", retry_after_seconds=60)
    )
    service = DiscoveryService(providers=[provider], cache=TTLCache())

    result = service.comments("https://video.example/video-1")

    assert result.success is False
    assert result.error_code == "risk_control"
    assert result.retry_after_seconds == 60


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "limit"),
        ({"limit": 51}, "limit"),
        ({"sort": "unknown"}, "sort"),
        ({"max_replies_per_thread": 0}, "max_replies_per_thread"),
        ({"max_replies_per_thread": 11}, "max_replies_per_thread"),
    ],
)
def test_comments_invalid_params_raise(kwargs, message):
    service = DiscoveryService(providers=[FakeCommentsProvider()], cache=TTLCache())

    with pytest.raises(DiscoveryError) as exc_info:
        service.comments("https://video.example/video-1", **kwargs)

    assert exc_info.value.code == "invalid_request"
    assert message in exc_info.value.message
