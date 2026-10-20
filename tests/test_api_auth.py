"""API 多消费者鉴权与限流测试（阶段 4）。"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.api.server import APIServer


@pytest.fixture(autouse=True)
def _clean_auth_env(monkeypatch):
    for name in ("VIDEOMIND_API_TOKEN", "VMB_CONSUMER_TOKENS", "VMB_RATE_LIMIT_PER_MIN"):
        monkeypatch.delenv(name, raising=False)


def _client(monkeypatch, **env) -> TestClient:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return TestClient(APIServer().app)


def test_no_tokens_keeps_local_mode(monkeypatch):
    with _client(monkeypatch) as client:
        assert client.get("/api/v1/status").status_code == 200


def test_admin_token_required_and_health_exempt(monkeypatch):
    with _client(monkeypatch, VIDEOMIND_API_TOKEN="admin-token") as client:
        assert client.get("/api/v1/status").status_code == 401
        assert client.get(
            "/api/v1/status",
            headers={"Authorization": "Bearer wrong"},
        ).status_code == 401
        assert client.get(
            "/api/v1/status",
            headers={"Authorization": "Bearer admin-token"},
        ).status_code == 200
        assert client.get("/health").status_code == 200


def test_consumer_tokens_are_accepted(monkeypatch):
    tokens = json.dumps({"content-ops": "tok-a", "n8n": "tok-b"})
    with _client(monkeypatch, VMB_CONSUMER_TOKENS=tokens) as client:
        assert client.get(
            "/api/v1/status",
            headers={"Authorization": "Bearer tok-a"},
        ).status_code == 200
        assert client.get(
            "/api/v1/status",
            headers={"Authorization": "Bearer tok-b"},
        ).status_code == 200
        assert client.get(
            "/api/v1/status",
            headers={"Authorization": "Bearer admin"},
        ).status_code == 401


def test_admin_and_consumer_coexist(monkeypatch):
    tokens = json.dumps({"content-ops": "tok-a"})
    with _client(
        monkeypatch,
        VIDEOMIND_API_TOKEN="admin-token",
        VMB_CONSUMER_TOKENS=tokens,
    ) as client:
        assert client.get(
            "/api/v1/status",
            headers={"Authorization": "Bearer admin-token"},
        ).status_code == 200
        assert client.get(
            "/api/v1/status",
            headers={"Authorization": "Bearer tok-a"},
        ).status_code == 200


def test_invalid_consumer_json_is_ignored(monkeypatch):
    with _client(
        monkeypatch,
        VIDEOMIND_API_TOKEN="admin-token",
        VMB_CONSUMER_TOKENS="{not-json",
    ) as client:
        assert client.get(
            "/api/v1/status",
            headers={"Authorization": "Bearer admin-token"},
        ).status_code == 200


def test_rate_limit_returns_429_with_retry_after(monkeypatch):
    headers = {"Authorization": "Bearer admin-token"}
    with _client(
        monkeypatch,
        VIDEOMIND_API_TOKEN="admin-token",
        VMB_RATE_LIMIT_PER_MIN="2",
    ) as client:
        assert client.get("/api/v1/status", headers=headers).status_code == 200
        assert client.get("/api/v1/status", headers=headers).status_code == 200

        limited = client.get("/api/v1/status", headers=headers)
        assert limited.status_code == 429
        assert int(limited.headers["Retry-After"]) >= 1

        # /health 不受限流影响
        assert client.get("/health").status_code == 200
