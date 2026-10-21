"""Gateway Console 路由与静态资产测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import APIServer


def test_root_redirects_to_console():
    with TestClient(APIServer().app) as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/console"


def test_console_is_served():
    with TestClient(APIServer().app) as client:
        response = client.get("/console")

    assert response.status_code == 200
    assert "Gateway Console" in response.text
    assert "/static/console/console.js" in response.text
    assert "Content-Security-Policy" in response.text or "content-security-policy" in response.text


def test_console_static_assets_are_served():
    with TestClient(APIServer().app) as client:
        script = client.get("/static/console/console.js")
        styles = client.get("/static/console/console.css")

    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert styles.status_code == 200
    assert "text/css" in styles.headers["content-type"]


def test_legacy_ui_is_available():
    with TestClient(APIServer().app) as client:
        response = client.get("/legacy")

    assert response.status_code == 200
    assert "VideoMind Bridge" in response.text
    assert "/static/app.js" in response.text
    assert 'href="/console"' in response.text


def test_console_is_public_but_api_requires_token(monkeypatch):
    monkeypatch.setenv("VIDEOMIND_API_TOKEN", "console-test-token")
    with TestClient(APIServer().app) as client:
        assert client.get("/console").status_code == 200
        assert client.get("/api/v1/metrics").status_code == 401
        authorized = client.get(
            "/api/v1/metrics",
            headers={"Authorization": "Bearer console-test-token"},
        )

    assert authorized.status_code == 200
