"""Discovery API 的路由开关、响应模型与 capabilities 测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api import discovery_routes
from src.api.server import APIServer
from src.core.capabilities import capabilities_payload
from src.core.discovery.models import (
    CommentItem,
    CommentsResult,
    CreatorFeedItem,
    CreatorFeedResult,
    CreatorRef,
)
from src.core.models import CostTier
from src.models.config import AsrConfig


class FakeService:
    def __init__(self, result: CreatorFeedResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def creator_feed(
        self,
        url: str,
        *,
        limit: int,
        max_cost: CostTier,
        request_id: str | None = None,
    ) -> CreatorFeedResult:
        self.calls.append(
            {
                "kind": "creator_feed",
                "url": url,
                "limit": limit,
                "max_cost": max_cost,
                "request_id": request_id,
            }
        )
        return self.result

    def comments(
        self,
        url: str,
        *,
        limit: int,
        sort: str,
        include_replies: bool,
        max_replies_per_thread: int,
        include_author: bool,
        max_cost: CostTier,
        request_id: str | None = None,
    ) -> CommentsResult:
        self.calls.append(
            {
                "kind": "comments",
                "url": url,
                "limit": limit,
                "sort": sort,
                "include_replies": include_replies,
                "max_replies_per_thread": max_replies_per_thread,
                "include_author": include_author,
                "max_cost": max_cost,
                "request_id": request_id,
            }
        )
        return _comments_success_result()


def _success_result() -> CreatorFeedResult:
    return CreatorFeedResult(
        success=True,
        platform="bilibili",
        source="bilibili_discovery",
        cost_tier=CostTier.FREE,
        creator=CreatorRef(
            id="123456",
            name="示例UP主",
            url="https://space.bilibili.com/123456",
        ),
        items=[
            CreatorFeedItem(
                id="BV1demo",
                url="https://www.bilibili.com/video/BV1demo",
                title="示例作品",
                published_at="2026-10-19T10:00:00+00:00",
                duration_seconds=120,
                metrics={"views": 100, "likes": 10},
                cover_url="https://i0.hdslb.com/demo.jpg",
            )
        ],
        completeness="full",
        has_more=True,
        fetched_at="2026-10-20T08:00:00+00:00",
        request_id="req-1",
    )


def _comments_success_result() -> CommentsResult:
    return CommentsResult(
        success=True,
        platform="bilibili",
        source="bilibili_discovery",
        cost_tier=CostTier.FREE,
        items=[
            CommentItem(
                id="c1",
                parent_id=None,
                root_id="c1",
                text="示例评论",
                likes=3,
                is_reply=False,
                reply_count=2,
            )
        ],
        completeness="full",
        sort="hot",
        has_more=True,
        fetched_at="2026-10-20T08:00:00+00:00",
        request_id="req-c1",
    )


def test_creator_feed_disabled_by_default(monkeypatch):
    monkeypatch.delenv("VMB_ENABLE_CREATOR_FEED", raising=False)
    server = APIServer()

    with TestClient(server.app) as client:
        response = client.post(
            "/api/v1/creator/feed",
            json={"url": "https://space.bilibili.com/123456"},
        )

    assert response.status_code == 404


def test_creator_feed_enabled_returns_structured_result(monkeypatch):
    monkeypatch.setenv("VMB_ENABLE_CREATOR_FEED", "1")
    fake = FakeService(_success_result())
    monkeypatch.setattr(discovery_routes, "_service", fake)
    server = APIServer()

    with TestClient(server.app) as client:
        response = client.post(
            "/api/v1/creator/feed",
            json={"url": "https://space.bilibili.com/123456", "limit": 10},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["creator"]["id"] == "123456"
    assert data["items"][0]["id"] == "BV1demo"
    assert data["items"][0]["metrics"] == {"views": 100, "likes": 10}
    assert data["returned_count"] == 1
    assert data["has_more"] is True
    assert "error" not in data

    assert fake.calls[0]["url"] == "https://space.bilibili.com/123456"
    assert fake.calls[0]["limit"] == 10
    assert fake.calls[0]["max_cost"] == CostTier.CHEAP
    assert isinstance(fake.calls[0]["request_id"], str)


def test_creator_feed_invalid_limit_returns_422(monkeypatch):
    monkeypatch.setenv("VMB_ENABLE_CREATOR_FEED", "1")
    server = APIServer()

    with TestClient(server.app) as client:
        response = client.post(
            "/api/v1/creator/feed",
            json={"url": "https://space.bilibili.com/123456", "limit": 0},
        )

    assert response.status_code == 422


def test_creator_feed_failure_omits_creator(monkeypatch):
    monkeypatch.setenv("VMB_ENABLE_CREATOR_FEED", "1")
    failure = CreatorFeedResult(
        success=False,
        platform="unknown",
        source="discovery",
        cost_tier=CostTier.CHEAP,
        completeness="none",
        fetched_at="2026-10-20T08:00:00+00:00",
        error="只支持已接入平台的创作者主页",
        error_code="not_supported",
        request_id="req-2",
    )
    monkeypatch.setattr(discovery_routes, "_service", FakeService(failure))
    server = APIServer()

    with TestClient(server.app) as client:
        response = client.post(
            "/api/v1/creator/feed",
            json={"url": "https://example.com/creator"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error_code"] == "not_supported"
    assert "creator" not in data


def test_comments_disabled_by_default(monkeypatch):
    monkeypatch.delenv("VMB_ENABLE_COMMENTS", raising=False)
    server = APIServer()

    with TestClient(server.app) as client:
        response = client.post(
            "/api/v1/comments",
            json={"url": "https://www.bilibili.com/video/BV1demo"},
        )

    assert response.status_code == 404


def test_comments_enabled_returns_structured_result(monkeypatch):
    monkeypatch.setenv("VMB_ENABLE_COMMENTS", "1")
    fake = FakeService(_success_result())
    monkeypatch.setattr(discovery_routes, "_service", fake)
    server = APIServer()

    with TestClient(server.app) as client:
        response = client.post(
            "/api/v1/comments",
            json={
                "url": "https://www.bilibili.com/video/BV1demo",
                "limit": 10,
                "sort": "recent",
                "include_replies": True,
                "max_replies_per_thread": 2,
                "include_author": True,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["sort"] == "hot"
    assert data["items"][0]["text"] == "示例评论"
    assert data["returned_count"] == 1
    assert data["top_level_count"] == 1
    assert data["reply_count"] == 0
    assert data["items"][0]["parent_id"] is None
    assert "author" not in data["items"][0]
    assert "error" not in data

    call = fake.calls[0]
    assert call["kind"] == "comments"
    assert call["limit"] == 10
    assert call["sort"] == "recent"
    assert call["include_replies"] is True
    assert call["include_author"] is True
    assert call["max_cost"] == CostTier.CHEAP


def test_comments_invalid_sort_returns_422(monkeypatch):
    monkeypatch.setenv("VMB_ENABLE_COMMENTS", "1")
    server = APIServer()

    with TestClient(server.app) as client:
        response = client.post(
            "/api/v1/comments",
            json={
                "url": "https://www.bilibili.com/video/BV1demo",
                "sort": "unknown",
            },
        )

    assert response.status_code == 422


@mock.patch("src.core.router.ContentRouter")
@mock.patch("src.core.asr.available_transcribers", return_value=[])
@mock.patch(
    "src.services.config_manager.ConfigManager.get_asr_config",
    return_value=AsrConfig(chain=["faster_whisper"], max_cost="premium"),
)
def test_capabilities_include_discovery_when_enabled(
    mock_cfg,
    mock_backends,
    mock_router,
    monkeypatch,
):
    monkeypatch.setenv("VMB_ENABLE_CREATOR_FEED", "1")
    monkeypatch.setenv("VMB_ENABLE_COMMENTS", "1")
    mock_router.return_value.list_extractors.return_value = {"bilibili": True}

    payload = capabilities_payload()

    assert payload["discovery"]["creator_feed"]["enabled"] is True
    assert payload["discovery"]["creator_feed"]["platforms"] == ["bilibili"]
    assert payload["discovery"]["creator_feed"]["limits"] == {
        "default": 20,
        "max": 30,
    }
    assert payload["discovery"]["comments"]["enabled"] is True
    assert payload["discovery"]["comments"]["platforms"] == ["bilibili"]
    assert payload["discovery"]["comments"]["limits"]["default"] == 20
    assert payload["discovery"]["comments"]["limits"]["max"] == 50
