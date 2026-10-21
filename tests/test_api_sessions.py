"""登录态状态与检查 API 测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.server import APIServer
from src.core.platforms.session import (
    SessionStatus,
    reset_session_manager,
)

_ENV_NAMES = (
    "VIDEOMIND_API_TOKEN",
    "VMB_CONSUMER_TOKENS",
    "VMB_BILIBILI_COOKIE",
    "VMB_BILIBILI_SESSDATA",
    "VMB_BILIBILI_COOKIES_FILE",
    "VMB_COOKIES_FILE",
    "DOUYIN_COOKIES_FILE",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    reset_session_manager()
    yield
    reset_session_manager()


def test_sessions_are_listed_and_redacted(monkeypatch):
    monkeypatch.setenv(
        "VMB_BILIBILI_COOKIE",
        "SESSDATA=super-secret; bili_jct=also-secret",
    )
    with TestClient(APIServer().app) as client:
        response = client.get("/api/v1/sessions")

    assert response.status_code == 200
    body = response.json()
    payload = {item["platform"]: item for item in body["sessions"]}
    assert payload["bilibili"]["configured"] is True
    assert payload["bilibili"]["source"] == "env"
    assert payload["bilibili"]["cookie_count"] == 2
    assert payload["douyin"]["configured"] is False
    assert "super-secret" not in response.text
    assert "also-secret" not in response.text


def test_check_unsupported_platform_returns_422():
    with TestClient(APIServer().app) as client:
        response = client.post("/api/v1/sessions/douyin/check")

    assert response.status_code == 422
    assert "不支持" in response.json()["detail"]


def test_check_bilibili_returns_status(monkeypatch):
    def fake_check(self) -> SessionStatus:
        return SessionStatus(
            platform="bilibili",
            configured=True,
            source="env",
            cookie_count=1,
            valid=True,
            last_checked="2026-10-21T00:00:00+00:00",
        )

    from src.core.platforms.session import BilibiliSessionProvider

    monkeypatch.setattr(BilibiliSessionProvider, "check", fake_check)
    with TestClient(APIServer().app) as client:
        response = client.post("/api/v1/sessions/bilibili/check")

    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert response.json()["platform"] == "bilibili"


def test_check_unknown_platform_returns_422():
    with TestClient(APIServer().app) as client:
        response = client.post("/api/v1/sessions/unknown/check")

    assert response.status_code == 422
