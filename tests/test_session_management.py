"""登录态统一管理 (批次C) 与 Origin 精确校验 (P0) 测试

覆盖:
- _is_allowed_origin: 前缀绕过回归 (127.0.0.1.evil.com) 与合法源放行
- SessionManager.resolve: 统一解析入口
- ConfigManager session 设置: keyring 存取
- 登录态优先级: 平台专用 env > keyring > 通用 env
- API 管理端点: admin 角色检查 / 路径校验
- MCP configure session:*
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient

from src.api.server import APIServer, _is_allowed_origin
from src.core.discovery.config import bilibili_cookie_header
from src.core.platforms.session import (
    BilibiliSessionProvider,
    YtDlpSessionProvider,
    get_session_manager,
    reset_session_manager,
)
from src.services.config_manager import ConfigManager


@pytest.fixture(autouse=True)
def _fresh_session_manager():
    reset_session_manager()
    yield
    reset_session_manager()


# ── P0: Origin 精确校验 ──────────────────────────────────────────


class TestOriginValidation:
    def test_prefix_spoofing_rejected(self):
        """回归: 前缀匹配绕过 http://127.0.0.1.evil.com 必须被拒绝"""
        assert _is_allowed_origin("http://127.0.0.1.evil.com") is False

    def test_localhost_subdomain_rejected(self):
        assert _is_allowed_origin("http://localhost.attacker.io") is False
        assert _is_allowed_origin("https://localhost.evil.cn") is False

    def test_local_hosts_allowed(self):
        assert _is_allowed_origin("http://127.0.0.1:8787") is True
        assert _is_allowed_origin("http://localhost") is True
        assert _is_allowed_origin("https://localhost:9443") is True
        assert _is_allowed_origin("http://[::1]:8787") is True

    def test_extension_schemes_allowed(self):
        assert _is_allowed_origin("chrome-extension://abcdefghijklmnop") is True
        assert _is_allowed_origin("moz-extension://uuid-here") is True

    def test_non_browser_and_garbage(self):
        assert _is_allowed_origin("") is True
        assert _is_allowed_origin("ftp://127.0.0.1") is False
        assert _is_allowed_origin("not-a-url") is False

    def test_api_rejects_spoofed_origin(self):
        """端到端: 仿冒 Origin 的 API 请求返回 403"""
        server = APIServer()
        with TestClient(server.app) as client:
            resp = client.get(
                "/api/v1/status",
                headers={"Origin": "http://127.0.0.1.evil.com"},
            )
            assert resp.status_code == 403

    def test_api_allows_local_origin(self):
        server = APIServer()
        with TestClient(server.app) as client:
            resp = client.get("/api/v1/status", headers={"Origin": "http://localhost:5173"})
            assert resp.status_code == 200


# ── SessionManager.resolve ───────────────────────────────────────


class TestSessionResolution:
    def test_resolve_ytdlp_returns_cookies_file(self, monkeypatch, tmp_path):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape HTTP Cookie File\n")
        monkeypatch.setenv("VMB_COOKIES_FILE", str(cookie_file))

        resolved = get_session_manager().resolve("ytdlp")
        assert resolved.cookies_file == str(cookie_file)
        assert resolved.ytdlp_args[:1] == ["--cookies"]
        assert resolved.source == "file"

    def test_resolve_ytdlp_browser(self, monkeypatch):
        monkeypatch.setenv("VMB_COOKIES_BROWSER", "chrome")
        resolved = get_session_manager().resolve("ytdlp")
        assert resolved.cookies_browser == "chrome"
        assert "--cookies-from-browser" in resolved.ytdlp_args

    def test_resolve_unknown_platform(self):
        resolved = get_session_manager().resolve("nonexistent")
        assert resolved.cookie_header is None
        assert resolved.source == "none"

    def test_resolve_bilibili_header(self, monkeypatch):
        monkeypatch.setenv("VMB_BILIBILI_COOKIE", "SESSDATA=abc; bili_jct=def")
        resolved = get_session_manager().resolve("bilibili")
        assert resolved.cookie_header == "SESSDATA=abc; bili_jct=def"


# ── ConfigManager 会话设置存取 ────────────────────────────────────


class TestSessionSettingsStorage:
    def test_set_get_delete_roundtrip(self):
        mgr = ConfigManager()
        key = "ytdlp:browser"
        try:
            assert mgr.set_session_setting(key, "firefox") is True
            assert mgr.get_session_setting(key) == "firefox"
            status = mgr.list_session_settings_status()
            assert status[key]["configured"] is True
        finally:
            mgr.delete_session_setting(key)
        assert mgr.get_session_setting(key) is None

    def test_unknown_key_rejected(self):
        mgr = ConfigManager()
        assert mgr.set_session_setting("unknown:key", "v") is False

    def test_empty_value_rejected(self):
        mgr = ConfigManager()
        assert mgr.set_session_setting("ytdlp:browser", "  ") is False


# ── 登录态来源优先级 ─────────────────────────────────────────────


class TestSessionPrecedence:
    def test_platform_env_beats_keyring(self, monkeypatch, tmp_path):
        """平台专用 env 优先于 keyring 存储的 cookies 文件"""
        stored = tmp_path / "stored.txt"
        stored.write_text("# Netscape HTTP Cookie File\n")
        mgr = ConfigManager()
        mgr.set_session_setting("bilibili:cookies_file", str(stored))
        try:
            monkeypatch.setenv("VMB_BILIBILI_COOKIES_FILE", str(tmp_path / "env.txt"))
            (tmp_path / "env.txt").write_text(
                ".bilibili.com\tTRUE\t/\tTRUE\t9999999999\tSESSDATA\tenv-sess\n"
            )
            provider = BilibiliSessionProvider()
            assert provider.status().source == "file"
            assert "env-sess" in provider.headers()["Cookie"]
        finally:
            mgr.delete_session_setting("bilibili:cookies_file")

    def test_keyring_file_falls_back_when_env_missing(self, monkeypatch, tmp_path):
        """env 未配置时使用 keyring 存储的 cookies 文件"""
        stored = tmp_path / "stored.txt"
        stored.write_text(
            ".bilibili.com\tTRUE\t/\tTRUE\t9999999999\tSESSDATA\tstored-sess\n"
        )
        mgr = ConfigManager()
        mgr.set_session_setting("bilibili:cookies_file", str(stored))
        try:
            monkeypatch.delenv("VMB_BILIBILI_COOKIES_FILE", raising=False)
            monkeypatch.delenv("VMB_COOKIES_FILE", raising=False)
            provider = BilibiliSessionProvider()
            assert "stored-sess" in provider.headers()["Cookie"]
        finally:
            mgr.delete_session_setting("bilibili:cookies_file")

    def test_ytdlp_browser_keyring_fallback(self, monkeypatch):
        """VMB_COOKIES_BROWSER 未设置时回退 keyring 的 ytdlp:browser"""
        mgr = ConfigManager()
        mgr.set_session_setting("ytdlp:browser", "edge")
        try:
            monkeypatch.delenv("VMB_COOKIES_BROWSER", raising=False)
            monkeypatch.delenv("VMB_COOKIES_FILE", raising=False)
            provider = YtDlpSessionProvider()
            assert provider.cookie_args() == ["--cookies-from-browser", "edge"]
        finally:
            mgr.delete_session_setting("ytdlp:browser")


# ── discovery 委托 SessionManager ────────────────────────────────


class TestDiscoveryDelegate:
    def test_bilibili_cookie_header_uses_env(self, monkeypatch):
        monkeypatch.setenv("VMB_BILIBILI_COOKIE", "SESSDATA=raw")
        assert bilibili_cookie_header() == "SESSDATA=raw"

    def test_bilibili_cookie_header_uses_sessdata(self, monkeypatch):
        monkeypatch.delenv("VMB_BILIBILI_COOKIE", raising=False)
        monkeypatch.setenv("VMB_BILIBILI_SESSDATA", "only-sess")
        assert bilibili_cookie_header() == "SESSDATA=only-sess"


# ── API 管理端点 ─────────────────────────────────────────────────


def _make_authed_server(monkeypatch, tmp_path):
    """多消费者鉴权模式: admin + 一个 consumer"""
    monkeypatch.setenv("VIDEOMIND_API_TOKEN", "admin-tok")
    monkeypatch.setenv("VMB_CONSUMER_TOKENS", '{"ops": "consumer-tok"}')
    return APIServer()


class TestSessionSettingsAPI:
    def test_consumer_forbidden(self, monkeypatch, tmp_path):
        server = _make_authed_server(monkeypatch, tmp_path)
        with TestClient(server.app) as client:
            resp = client.put(
                "/api/v1/sessions/settings/ytdlp:browser",
                json={"value": "chrome"},
                headers={"Authorization": "Bearer consumer-tok"},
            )
            assert resp.status_code == 403

    def test_admin_allowed(self, monkeypatch, tmp_path):
        server = _make_authed_server(monkeypatch, tmp_path)
        mgr = ConfigManager()
        try:
            with TestClient(server.app) as client:
                resp = client.put(
                    "/api/v1/sessions/settings/ytdlp:browser",
                    json={"value": "chrome"},
                    headers={"Authorization": "Bearer admin-tok"},
                )
                assert resp.status_code == 200
                assert mgr.get_session_setting("ytdlp:browser") == "chrome"
        finally:
            mgr.delete_session_setting("ytdlp:browser")

    def test_cookies_file_must_exist(self, monkeypatch, tmp_path):
        server = _make_authed_server(monkeypatch, tmp_path)
        with TestClient(server.app) as client:
            resp = client.put(
                "/api/v1/sessions/settings/bilibili:cookies_file",
                json={"value": str(tmp_path / "nope.txt")},
                headers={"Authorization": "Bearer admin-tok"},
            )
            assert resp.status_code == 400

    def test_unknown_key_rejected(self, monkeypatch, tmp_path):
        server = _make_authed_server(monkeypatch, tmp_path)
        with TestClient(server.app) as client:
            resp = client.put(
                "/api/v1/sessions/settings/evil:key",
                json={"value": "x"},
                headers={"Authorization": "Bearer admin-tok"},
            )
            assert resp.status_code == 400

    def test_local_mode_without_auth_allowed(self, monkeypatch, tmp_path):
        """未启用鉴权的本地模式放行 (与 settings 端点一致)"""
        monkeypatch.delenv("VIDEOMIND_API_TOKEN", raising=False)
        monkeypatch.delenv("VMB_CONSUMER_TOKENS", raising=False)
        server = APIServer()
        mgr = ConfigManager()
        try:
            with TestClient(server.app) as client:
                resp = client.put(
                    "/api/v1/sessions/settings/ytdlp:browser",
                    json={"value": "firefox"},
                )
                assert resp.status_code == 200
        finally:
            mgr.delete_session_setting("ytdlp:browser")

    def test_settings_endpoint_requires_admin(self, monkeypatch, tmp_path):
        """P1-1: 消费者不得改 settings (含 ai_base_url 窃取 Key 的路径)"""
        server = _make_authed_server(monkeypatch, tmp_path)
        with TestClient(server.app) as client:
            resp = client.put(
                "/api/v1/settings",
                json={"ai_base_url": "https://evil.example.com"},
                headers={"Authorization": "Bearer consumer-tok"},
            )
            assert resp.status_code == 403


# ── MCP configure session:* ──────────────────────────────────────


class TestMcpConfigureSessions:
    def _make_server(self):
        from src.mcp.server import MCPServer

        return MCPServer()

    def test_set_session_cookies_file_validates_path(self, tmp_path):
        server = self._make_server()
        result = server._call_configure({
            "action": "set",
            "key": "session:bilibili:cookies_file",
            "value": str(tmp_path / "nope.txt"),
        })
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_set_and_get_session_setting(self, tmp_path):
        server = self._make_server()
        cookie_file = tmp_path / "c.txt"
        cookie_file.write_text("# Netscape HTTP Cookie File\n")
        try:
            result = server._call_configure({
                "action": "set",
                "key": "session:bilibili:cookies_file",
                "value": str(cookie_file),
            })
            assert result["success"] is True

            got = server._call_configure({"action": "get"})
            assert got["success"] is True
            assert got["config"]["session_settings"]["bilibili:cookies_file"]["configured"] is True
        finally:
            ConfigManager().delete_session_setting("bilibili:cookies_file")

    def test_delete_session_setting(self):
        server = self._make_server()
        mgr = ConfigManager()
        mgr.set_session_setting("ytdlp:browser", "chrome")
        result = server._call_configure({"action": "delete", "key": "session:ytdlp:browser"})
        assert result["success"] is True
        assert mgr.get_session_setting("ytdlp:browser") is None

    def test_unknown_session_key_rejected(self):
        server = self._make_server()
        result = server._call_configure({
            "action": "set", "key": "session:evil:key", "value": "x",
        })
        assert result["success"] is False
