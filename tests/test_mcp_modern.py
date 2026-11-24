"""MCP 实现测试（2026-11-25，A2 之后）。

形态唯一：**薄适配器** —— 工具只做参数翻译，经 HTTP 调本机 REST(:8787)。
这里锁住四件事：

1. 工具面固定 3 个（extract / capabilities / comments）；
2. 参数翻译正确（成本档、asr 语言、prescreen 走不同端点）；
3. 服务没起时给出可执行提示，而不是裸 traceback；
4. **不存在第二实现** —— embedded / legacy 两条兜底已于 2026-11-25 删除，
   再出现就等于 L3 又持有引擎了。
"""

from __future__ import annotations

import inspect
import pathlib

import httpx
import pytest

from src.mcp import modern_server

_TOOL_NAMES = {"extract", "capabilities", "comments"}


def _tools(server) -> dict:
    return server._tool_manager._tools


# ── 工具面与形态 ────────────────────────────────────────────────────────


def test_tool_surface_is_three():
    assert set(_tools(modern_server.build_server())) == _TOOL_NAMES


def test_build_server_has_no_mode_switch():
    """build_server() 不再接受 embedded 参数：只有一种形态，没有"另一个人格"。"""
    assert list(inspect.signature(modern_server.build_server).parameters) == []


def test_no_second_implementation_remains():
    """兜底实现必须真的没了 —— 文档里提历史可以，代码里不许再有第二条路。"""
    src = pathlib.Path(modern_server.__file__).read_text()
    assert "def _build_embedded" not in src, "进程内引擎兜底已删除"
    assert "def _embedded_enabled" not in src, "embedded 开关已删除"
    assert "from .server import" not in src, "不得再依赖 src.mcp.server 的实现"
    assert not hasattr(modern_server, "_embedded_enabled")


# ── 参数翻译 ────────────────────────────────────────────────────────────


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
    tool = _tools(modern_server.build_server())["extract"]
    tool.fn(url="https://www.douyin.com/video/1", cost_tier="cheap", asr_language="zh")

    method, path, payload = captured[-1]
    assert (method, path) == ("POST", "/api/v1/extract")
    assert payload == {
        "url": "https://www.douyin.com/video/1",
        "cost_tier": "cheap",
        "asr_options": {"language": "zh"},
    }


def test_extract_prescreen_uses_prescreen_endpoint(captured):
    tool = _tools(modern_server.build_server())["extract"]
    tool.fn(url="https://www.douyin.com/video/1", mode="prescreen")

    method, path, payload = captured[-1]
    assert (method, path) == ("POST", "/api/v1/prescreen")
    assert payload == {"url": "https://www.douyin.com/video/1", "mode": "quick"}


def test_extract_rejects_unknown_mode(captured):
    tool = _tools(modern_server.build_server())["extract"]
    with pytest.raises(ValueError):
        tool.fn(url="https://x/v", mode="whatever")


def test_capabilities_and_comments_paths(captured):
    tools = _tools(modern_server.build_server())
    tools["capabilities"].fn()
    assert captured[-1][:2] == ("GET", "/api/v1/capabilities")

    tools["comments"].fn(url="https://www.douyin.com/video/1", limit=5, sort="time")
    method, path, payload = captured[-1]
    assert (method, path) == ("POST", "/api/v1/comments")
    assert payload == {"url": "https://www.douyin.com/video/1", "limit": 5, "sort": "time"}


# ── 失败提示 ────────────────────────────────────────────────────────────


def test_connection_error_is_actionable(monkeypatch):
    """服务没起时必须告诉人「怎么办」，并明确不再有离线兜底。"""

    def _boom(self, method, url, **kwargs):
        raise httpx.ConnectError("refused", request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.Client, "request", _boom)
    with pytest.raises(RuntimeError) as exc:
        modern_server._request("POST", "/api/v1/extract", {"url": "x"})

    msg = str(exc.value)
    assert "pm2 start videomind-api" in msg, "要给出可执行动作"
    assert "/health" in msg, "要给出自检方式"
    assert "VMB_MCP_EMBEDDED" not in msg, "兜底已删除，不许再提示一个不存在的开关"


# ── 入口 ────────────────────────────────────────────────────────────────


def test_entry_point_delegates_to_modern(monkeypatch):
    """DSH 用 -m src.mcp.server 启动，入口必须转调薄适配器。"""
    import src.mcp.server as entry

    calls: list[str] = []
    monkeypatch.setattr(modern_server, "main", lambda: calls.append("modern"))

    entry.main()
    assert calls == ["modern"]
