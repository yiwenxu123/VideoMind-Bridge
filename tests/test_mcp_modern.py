"""MCP 实现测试（2026-11-24）。

当前形态：**薄适配器**（把请求转给本机 REST :8787），可选 `VMB_MCP_EMBEDDED=1`
退回进程内引擎。这里锁住四件事：

1. 工具面固定为 3 个，且两条路径的工具面一致；
2. 远程路径的**参数翻译**正确（成本档、asr 语言、prescreen 走不同端点）；
3. 服务没起时给出可执行提示，而不是裸 traceback；
4. 嵌入式路径与旧实现结果一致（兜底不许漂移）。
"""

from __future__ import annotations

import httpx
import pytest

from src.mcp import modern_server

_TOOL_NAMES = {"extract", "capabilities", "comments"}


def _tools(server) -> dict:
    return server._tool_manager._tools


# ── 工具面 ──────────────────────────────────────────────────────────────


def test_remote_surface_is_the_agreed_three():
    assert set(_tools(modern_server.build_server(embedded=False))) == _TOOL_NAMES


def test_embedded_surface_matches_remote():
    """兜底路径与默认路径的工具面必须一致，否则切换时 Agent 会调不到。"""
    remote = set(_tools(modern_server.build_server(embedded=False)))
    embedded = set(_tools(modern_server.build_server(embedded=True)))
    assert remote == embedded == _TOOL_NAMES


def test_build_server_defaults_to_remote(monkeypatch):
    monkeypatch.delenv("VMB_MCP_EMBEDDED", raising=False)
    assert modern_server._embedded_enabled() is False
    monkeypatch.setenv("VMB_MCP_EMBEDDED", "1")
    assert modern_server._embedded_enabled() is True


# ── 远程路径：参数翻译 ──────────────────────────────────────────────────


@pytest.fixture
def captured(monkeypatch):
    """拦截 _request，记录 (method, path, payload)。"""
    calls: list[tuple[str, str, dict | None]] = []

    def _fake(method: str, path: str, payload: dict | None = None):
        calls.append((method, path, payload))
        return {"ok": True, "path": path}

    monkeypatch.setattr(modern_server, "_request", _fake)
    return calls


def test_extract_translates_to_rest_extract(captured):
    tool = _tools(modern_server.build_server(embedded=False))["extract"]
    tool.fn(url="https://www.douyin.com/video/1", cost_tier="cheap", asr_language="zh")

    method, path, payload = captured[-1]
    assert (method, path) == ("POST", "/api/v1/extract")
    assert payload == {
        "url": "https://www.douyin.com/video/1",
        "cost_tier": "cheap",
        "asr_options": {"language": "zh"},
    }


def test_extract_prescreen_uses_prescreen_endpoint(captured):
    tool = _tools(modern_server.build_server(embedded=False))["extract"]
    tool.fn(url="https://www.douyin.com/video/1", mode="prescreen")

    method, path, payload = captured[-1]
    assert (method, path) == ("POST", "/api/v1/prescreen")
    assert payload == {"url": "https://www.douyin.com/video/1", "mode": "quick"}


def test_extract_rejects_unknown_mode(captured):
    tool = _tools(modern_server.build_server(embedded=False))["extract"]
    with pytest.raises(ValueError):
        tool.fn(url="https://x/v", mode="whatever")


def test_capabilities_and_comments_paths(captured):
    tools = _tools(modern_server.build_server(embedded=False))
    tools["capabilities"].fn()
    assert captured[-1][:2] == ("GET", "/api/v1/capabilities")

    tools["comments"].fn(url="https://www.douyin.com/video/1", limit=5, sort="time")
    method, path, payload = captured[-1]
    assert (method, path) == ("POST", "/api/v1/comments")
    assert payload == {"url": "https://www.douyin.com/video/1", "limit": 5, "sort": "time"}


# ── 远程路径：失败提示 ──────────────────────────────────────────────────


def test_connection_error_is_actionable(monkeypatch):
    """服务没起时必须告诉人「怎么办」，这是薄适配器唯一的代价。"""

    def _boom(self, method, url, **kwargs):
        raise httpx.ConnectError(
            "refused", request=httpx.Request(method, url)
        )

    # 直接测 _request 的异常转换
    monkeypatch.setattr(httpx.Client, "request", _boom)
    with pytest.raises(RuntimeError) as exc:
        modern_server._request("POST", "/api/v1/extract", {"url": "x"})

    msg = str(exc.value)
    assert "pm2 start videomind-api" in msg, "要给出可执行动作"
    assert "VMB_MCP_EMBEDDED=1" in msg, "要给出离线兜底选项"


# ── 嵌入式路径：与旧实现一致 ────────────────────────────────────────────


def test_embedded_capabilities_matches_legacy():
    from src.mcp.server import MCPServer as LegacyCore

    legacy = LegacyCore()._call_capabilities({})
    modern = _tools(modern_server.build_server(embedded=True))["capabilities"].fn()
    assert modern == legacy


def test_embedded_prescreen_matches_legacy():
    from src.mcp.server import MCPServer as LegacyCore

    url = "https://www.bilibili.com/video/BV1x"
    legacy = LegacyCore()._call_prescreen_video({"url": url, "mode": "quick"})
    modern = _tools(modern_server.build_server(embedded=True))["extract"].fn(
        url=url, mode="prescreen"
    )
    assert modern == legacy


# ── 入口 ────────────────────────────────────────────────────────────────


def test_entry_point_defaults_to_modern_and_keeps_legacy_escape_hatch(monkeypatch):
    """`server.main()` 默认走新实现；VMB_MCP_LEGACY=1 时退回手写 JSON-RPC 版。"""
    import src.mcp.server as legacy_module

    calls: list[str] = []
    monkeypatch.setattr(modern_server, "main", lambda: calls.append("modern"))

    class _StubLegacy:
        def run(self) -> None:
            calls.append("legacy")

        def close(self) -> None:
            pass

    monkeypatch.setattr(legacy_module, "MCPServer", _StubLegacy)

    monkeypatch.delenv("VMB_MCP_LEGACY", raising=False)
    legacy_module.main()
    assert calls == ["modern"]

    calls.clear()
    monkeypatch.setenv("VMB_MCP_LEGACY", "1")
    legacy_module.main()
    assert calls == ["legacy"]
