"""Discovery 真实链接脚本的清单解析与结果判定测试。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_discovery_links.py"
_SPEC = importlib.util.spec_from_file_location("_vmb_check_discovery_links", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
check_discovery_links = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_discovery_links)


class FakeResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self.body = body

    def json(self) -> dict[str, Any]:
        return self.body


class FakeClient:
    def __init__(self, body: dict[str, Any]) -> None:
        self.body = body
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, json: dict[str, Any], timeout: float) -> FakeResponse:
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(self.body)


def test_load_manifest_defaults(tmp_path: Path):
    manifest = tmp_path / "links.yaml"
    manifest.write_text(
        """
- name: creator
  url: "https://space.bilibili.com/123456"
- name: comments
  kind: comments
  url: "https://www.bilibili.com/video/BV1demo"
  sort: recent
  include_replies: true
""",
        encoding="utf-8",
    )

    entries = check_discovery_links.load_manifest(manifest)

    assert entries[0]["kind"] == "creator_feed"
    assert entries[0]["limit"] == 5
    assert entries[1]["kind"] == "comments"
    assert entries[1]["limit"] == 10
    assert entries[1]["sort"] == "recent"
    assert entries[1]["include_replies"] is True


def test_check_one_success():
    client = FakeClient(
        {
            "success": True,
            "returned_count": 3,
            "top_level_count": 1,
            "reply_count": 2,
            "completeness": "partial",
            "has_more": True,
            "request_id": "req-1",
        }
    )
    entry = {
        "name": "comments",
        "kind": "comments",
        "url": "https://www.bilibili.com/video/BV1demo",
        "limit": 10,
        "min_items": 1,
        "sort": "hot",
        "include_replies": True,
        "max_replies_per_thread": 2,
        "include_author": False,
    }

    row = check_discovery_links.check_one(
        client,
        "http://127.0.0.1:8787",
        entry,
        30,
    )

    assert row["ok"] is True
    assert row["returned_count"] == 3
    assert row["top_level_count"] == 1
    assert row["reply_count"] == 2
    assert row["completeness"] == "partial"
    assert client.calls[0]["url"] == "http://127.0.0.1:8787/api/v1/comments"
    assert client.calls[0]["json"]["sort"] == "hot"
    assert client.calls[0]["json"]["include_author"] is False


def test_check_one_failure():
    client = FakeClient(
        {
            "success": False,
            "returned_count": 0,
            "error_code": "risk_control",
            "error": "B站风控",
        }
    )
    entry = {
        "name": "creator",
        "kind": "creator_feed",
        "url": "https://space.bilibili.com/123456",
        "limit": 5,
        "min_items": 1,
    }

    row = check_discovery_links.check_one(
        client,
        "http://127.0.0.1:8787",
        entry,
        30,
    )

    assert row["ok"] is False
    assert row["error_code"] == "risk_control"
    assert row["error"] == "B站风控"
