"""BilibiliDiscoveryProvider 的 URL 解析、字段映射与错误映射测试。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.core.discovery.models import DiscoveryError
from src.core.discovery.providers.bilibili import BilibiliDiscoveryProvider

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "discovery"
    / "bilibili_space_search.json"
)


class FakeClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.headers: dict[str, str] | None = None

    def wbi_get(
        self,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((path, params))
        self.headers = headers
        return self.payload


def _payload() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _provider(payload: dict[str, Any]) -> tuple[BilibiliDiscoveryProvider, FakeClient]:
    client = FakeClient(payload)
    return BilibiliDiscoveryProvider(client=client), client


def test_supports_creator_url_variants():
    provider, _ = _provider({"code": 0, "data": {}})

    assert provider.supports_creator_url("https://space.bilibili.com/123456")
    assert provider.supports_creator_url("https://space.bilibili.com/123456/video")
    assert provider.supports_creator_url("https://www.bilibili.com/space/123456")
    assert provider.supports_creator_url("https://m.bilibili.com/space/123456")

    assert not provider.supports_creator_url("https://www.bilibili.com/video/BV1xx")
    assert not provider.supports_creator_url("https://space.bilibili.com/not-a-mid")
    assert not provider.supports_creator_url("https://example.com/space/123456")


def test_fetch_creator_feed_maps_items_and_metrics():
    provider, client = _provider(_payload())

    result = provider.fetch_creator_feed(
        "https://space.bilibili.com/123456",
        limit=2,
    )

    assert result.success is True
    assert result.platform == "bilibili"
    assert result.source == "bilibili_discovery"
    assert result.creator is not None
    assert result.creator.id == "123456"
    assert result.creator.name == "示例UP主"
    assert result.creator.url == "https://space.bilibili.com/123456"
    assert result.has_more is True
    assert result.warnings == []
    assert len(result.items) == 2

    first = result.items[0]
    assert first.id == "BV1demo00001"
    assert first.url == "https://www.bilibili.com/video/BV1demo00001"
    assert first.title == "示例视频 AI"
    assert first.published_at == datetime.fromtimestamp(
        1760000000, tz=UTC
    ).isoformat(timespec="seconds")
    assert first.duration_seconds == 754
    assert first.metrics == {
        "views": 12000,
        "likes": 800,
        "comments": 60,
        "favorites": 300,
        "coins": 50,
        "shares": 40,
    }
    assert first.cover_url == "https://i0.hdslb.com/bfs/archive/demo1.jpg"

    second = result.items[1]
    assert second.duration_seconds == 3723
    assert second.cover_url == "https://i0.hdslb.com/bfs/archive/demo2.jpg"

    assert client.calls[0][0] == "/x/space/wbi/arc/search"
    assert client.calls[0][1]["mid"] == "123456"
    assert client.calls[0][1]["ps"] == "2"
    assert client.calls[0][1]["pn"] == "1"
    assert client.headers == {
        "Referer": "https://space.bilibili.com/123456",
        "Origin": "https://space.bilibili.com",
    }


def test_fetch_creator_feed_handles_int_duration_and_missing_pic():
    provider, _ = _provider(_payload())

    result = provider.fetch_creator_feed(
        "https://space.bilibili.com/123456",
        limit=3,
    )

    third = result.items[2]
    assert third.duration_seconds == 95
    assert third.metrics == {}
    assert third.cover_url is None


def test_fetch_creator_feed_empty_list():
    provider, _ = _provider(
        {
            "code": 0,
            "data": {"list": {"vlist": []}, "page": {"count": 0}},
        }
    )

    result = provider.fetch_creator_feed(
        "https://space.bilibili.com/123456",
        limit=20,
    )

    assert result.success is True
    assert result.items == []
    assert result.has_more is False
    assert result.creator is not None
    assert result.creator.name == ""
    assert result.warnings == ["creator_name_unavailable"]


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (-352, "risk_control"),
        (-412, "risk_control"),
        (-401, "auth_required"),
        (-404, "creator_not_found"),
        (-500, "upstream_error"),
    ],
)
def test_fetch_creator_feed_maps_api_error_codes(code: int, expected: str):
    provider, _ = _provider({"code": code, "message": "api error"})

    with pytest.raises(DiscoveryError) as exc_info:
        provider.fetch_creator_feed("https://space.bilibili.com/123456", limit=20)

    assert exc_info.value.code == expected


def test_fetch_creator_feed_malformed_data_raises_upstream_error():
    provider, _ = _provider({"code": 0, "data": []})

    with pytest.raises(DiscoveryError) as exc_info:
        provider.fetch_creator_feed("https://space.bilibili.com/123456", limit=20)

    assert exc_info.value.code == "upstream_error"


def test_fetch_creator_feed_rejects_invalid_url():
    provider, _ = _provider({"code": 0, "data": {}})

    with pytest.raises(DiscoveryError) as exc_info:
        provider.fetch_creator_feed("https://www.bilibili.com/video/BV1xx", limit=20)

    assert exc_info.value.code == "invalid_request"


class RaisingClient:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def wbi_get(
        self,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request = httpx.Request(
            "GET",
            f"https://api.bilibili.com{path}",
        )
        response = httpx.Response(self.status_code, request=request)
        raise httpx.HTTPStatusError(
            "upstream error",
            request=request,
            response=response,
        )


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, "auth_required"),
        (403, "risk_control"),
        (412, "risk_control"),
        (429, "rate_limited"),
    ],
)
def test_fetch_creator_feed_maps_http_status(status_code: int, expected: str):
    provider = BilibiliDiscoveryProvider(client=RaisingClient(status_code))

    with pytest.raises(DiscoveryError) as exc_info:
        provider.fetch_creator_feed("https://space.bilibili.com/123456", limit=20)

    assert exc_info.value.code == expected


def test_fetch_creator_feed_412_mentions_cookie_file():
    provider = BilibiliDiscoveryProvider(client=RaisingClient(412))

    with pytest.raises(DiscoveryError) as exc_info:
        provider.fetch_creator_feed("https://space.bilibili.com/123456", limit=20)

    assert "VMB_BILIBILI_COOKIES_FILE" in exc_info.value.message
    assert exc_info.value.retry_after_seconds == 60
