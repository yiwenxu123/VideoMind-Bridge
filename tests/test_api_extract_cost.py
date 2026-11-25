"""API /extract 的 cost_tier 透传与校验。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import APIServer
from src.core.models import CostTier, ExtractResult


def _result() -> ExtractResult:
    return ExtractResult(
        success=True,
        platform="mock",
        title="标题",
        content="正文",
        source="mock",
        url="https://example.com/v",
        cost_tier=CostTier.FREE,
        completeness="full",
    )


def test_extract_cost_tier_default_and_premium():
    server = APIServer()
    calls: list[CostTier] = []

    def fake_extract(url, *, max_cost=None, options=None):
        calls.append(max_cost)
        return _result()

    server._router_runtime.extract = fake_extract

    with TestClient(server.app) as client:
        default = client.post("/api/v1/extract", json={"url": "https://example.com/v"})
        premium = client.post(
            "/api/v1/extract",
            json={"url": "https://example.com/v", "cost_tier": "premium"},
        )

    assert default.status_code == 200
    assert premium.status_code == 200
    assert calls == [CostTier.CHEAP, CostTier.PREMIUM]

    # 服务端替调用方决定"最多花到 cheap"这件事必须可见，不能静默。
    assert default.json()["cost_tier_source"] == "default"
    assert premium.json()["cost_tier_source"] == "request"


def test_archive_reports_cost_tier_source():
    server = APIServer()

    def fake_extract(url, *, max_cost=None, options=None):
        return _result()

    server._router_runtime.extract = fake_extract

    with TestClient(server.app) as client:
        default = client.post(
            "/api/v1/extract/archive",
            json={"url": "https://example.com/v", "targets": ["local"]},
        )
        explicit = client.post(
            "/api/v1/extract/archive",
            json={"url": "https://example.com/v", "targets": ["local"], "cost_tier": "free"},
        )

    assert default.json()["cost_tier_source"] == "default"
    assert explicit.json()["cost_tier_source"] == "request"


def test_extract_invalid_cost_tier_returns_400():
    server = APIServer()

    with TestClient(server.app) as client:
        response = client.post(
            "/api/v1/extract",
            json={"url": "https://example.com/v", "cost_tier": "unknown"},
        )

    assert response.status_code == 400


def test_app_shutdown_closes_router_runtime(monkeypatch):
    server = APIServer()
    closed: list[bool] = []
    monkeypatch.setattr(
        server._router_runtime,
        "close",
        lambda: closed.append(True),
    )

    with TestClient(server.app):
        pass

    assert closed == [True]
