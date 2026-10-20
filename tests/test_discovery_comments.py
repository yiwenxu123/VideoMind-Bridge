"""BilibiliDiscoveryProvider 评论采样测试。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from src.core.discovery.models import DiscoveryError
from src.core.discovery.providers.bilibili import BilibiliDiscoveryProvider
from src.core.discovery.throttle import PlatformThrottle

FIXTURES = Path(__file__).parent / "fixtures" / "discovery"


class FakeClient:
    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("get", path, params or {}))
        response = self.responses[path]
        if isinstance(response, Exception):
            raise response
        return response

    def wbi_get(
        self,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("wbi", path, params))
        response = self.responses[path]
        if isinstance(response, Exception):
            raise response
        return response


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _provider(
    responses: dict[str, dict[str, Any]],
) -> tuple[BilibiliDiscoveryProvider, FakeClient]:
    client = FakeClient(responses)
    provider = BilibiliDiscoveryProvider(
        client=client,
        throttle=PlatformThrottle({"bilibili": 0}),
    )
    return provider, client


def test_supports_comments_variants():
    provider, _ = _provider({})

    assert provider.supports_comments("https://www.bilibili.com/video/BV1demo")
    assert provider.supports_comments("https://m.bilibili.com/video/av123")
    assert not provider.supports_comments("https://space.bilibili.com/123456")
    assert not provider.supports_comments("https://example.com/video/BV1demo")


def test_fetch_comments_parses_top_level_and_replies():
    responses = {
        "/x/web-interface/view": {"code": 0, "data": {"aid": 123}},
        "/x/v2/reply": _load("bilibili_comments.json"),
        "/x/v2/reply/reply": _load("bilibili_replies.json"),
    }
    provider, client = _provider(responses)

    result = provider.fetch_comments(
        "https://www.bilibili.com/video/BV1demo",
        limit=10,
        sort="hot",
        include_replies=True,
        max_replies_per_thread=3,
        include_author=False,
    )

    assert result.success is True
    assert result.platform == "bilibili"
    assert result.sort == "hot"
    assert result.completeness == "partial"
    assert result.warnings == ["replies_truncated"]
    assert result.has_more is True
    assert len(result.items) == 3

    top = result.items[0]
    assert top.id == "10001"
    assert top.parent_id is None
    assert top.root_id == "10001"
    assert top.text == "这个观点很有启发"
    assert top.likes == 42
    assert top.created_at == datetime.fromtimestamp(
        1760000000, tz=UTC
    ).isoformat(timespec="seconds")
    assert top.is_reply is False
    assert top.reply_count == 5
    assert top.author_display_name is None

    reply = result.items[2]
    assert reply.id == "20001"
    assert reply.parent_id == "10001"
    assert reply.root_id == "10001"
    assert reply.is_reply is True

    payload = result.to_dict()
    assert payload["returned_count"] == 3
    assert payload["top_level_count"] == 2
    assert payload["reply_count"] == 1
    assert "author" not in payload["items"][0]
    assert "mid" not in json.dumps(payload, ensure_ascii=False)

    assert client.calls[0][0] == "wbi"
    assert client.calls[0][1] == "/x/web-interface/view"
    assert client.calls[1][1] == "/x/v2/reply"
    assert client.calls[1][2]["sort"] == "2"
    assert client.calls[1][2]["oid"] == "123"
    assert client.calls[2][1] == "/x/v2/reply/reply"
    assert client.calls[2][2]["root"] == "10001"


def test_fetch_comments_include_author_only_returns_display_name():
    responses = {
        "/x/web-interface/view": {"code": 0, "data": {"aid": 123}},
        "/x/v2/reply": _load("bilibili_comments.json"),
    }
    provider, _ = _provider(responses)

    result = provider.fetch_comments(
        "https://www.bilibili.com/video/BV1demo",
        limit=2,
        sort="recent",
        include_replies=False,
        max_replies_per_thread=3,
        include_author=True,
    )

    assert result.items[0].author_display_name == "用户甲"
    payload = result.to_dict()
    assert payload["items"][0]["author"] == {"display_name": "用户甲"}
    assert "mid" not in json.dumps(payload, ensure_ascii=False)
    assert result.sort == "recent"


def test_fetch_comments_av_url_skips_view_request():
    responses = {"/x/v2/reply": _load("bilibili_comments.json")}
    provider, client = _provider(responses)

    result = provider.fetch_comments(
        "https://www.bilibili.com/video/av456",
        limit=2,
        sort="hot",
        include_replies=False,
        max_replies_per_thread=3,
        include_author=False,
    )

    assert result.success is True
    assert len(client.calls) == 1
    assert client.calls[0][1] == "/x/v2/reply"
    assert client.calls[0][2]["oid"] == "456"


def test_fetch_comments_truncates_long_text():
    payload = _load("bilibili_comments.json")
    payload["data"]["replies"][0]["content"]["message"] = "x" * 2100
    responses = {
        "/x/web-interface/view": {"code": 0, "data": {"aid": 123}},
        "/x/v2/reply": payload,
    }
    provider, _ = _provider(responses)

    result = provider.fetch_comments(
        "https://www.bilibili.com/video/BV1demo",
        limit=1,
        sort="hot",
        include_replies=False,
        max_replies_per_thread=3,
        include_author=False,
    )

    item = result.items[0]
    assert len(item.text) == 2000
    assert item.truncated is True
    assert result.to_dict()["items"][0]["truncated"] is True


def test_fetch_comments_reply_failure_returns_partial():
    responses = {
        "/x/web-interface/view": {"code": 0, "data": {"aid": 123}},
        "/x/v2/reply": _load("bilibili_comments.json"),
        "/x/v2/reply/reply": DiscoveryError("risk_control", "风控"),
    }
    provider, _ = _provider(responses)

    result = provider.fetch_comments(
        "https://www.bilibili.com/video/BV1demo",
        limit=10,
        sort="hot",
        include_replies=True,
        max_replies_per_thread=3,
        include_author=False,
    )

    assert result.success is True
    assert result.completeness == "partial"
    assert "reply_fetch_partial" in result.warnings
    assert len(result.items) == 2


def test_fetch_comments_risk_control_on_top_level_raises():
    responses = {
        "/x/web-interface/view": {"code": 0, "data": {"aid": 123}},
        "/x/v2/reply": {"code": -352, "message": "风控校验失败"},
    }
    provider, _ = _provider(responses)

    with pytest.raises(DiscoveryError) as exc_info:
        provider.fetch_comments(
            "https://www.bilibili.com/video/BV1demo",
            limit=10,
            sort="hot",
            include_replies=False,
            max_replies_per_thread=3,
            include_author=False,
        )

    assert exc_info.value.code == "risk_control"
