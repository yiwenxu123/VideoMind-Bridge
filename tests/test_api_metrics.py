"""平台请求指标端点测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import APIServer


def test_metrics_endpoint_returns_platform_counters():
    with TestClient(APIServer().app) as client:
        response = client.get("/api/v1/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert "enabled" in body
    platforms = body["platforms"]
    assert {"bilibili", "douyin", "xiaohongshu", "youtube"} <= set(platforms)
    bilibili = platforms["bilibili"]
    assert bilibili["requests_total"] == 0
    assert bilibili["success_total"] == 0
    assert bilibili["failure_streak"] == 0
    assert bilibili["cooldown_remaining_s"] == 0
    assert bilibili["last_error_code"] is None
    assert bilibili["circuit"] == "closed"
    assert "SESSDATA" not in response.text
    assert "cookie" not in response.text.lower()
