"""MCP 新实现（mcp 2.x MCPServer）测试（2026-11-22）。

迁移动机是三个**功能性**缺陷（旧手写 JSON-RPC 实现）：
1. 单线程 ``for line in sys.stdin``：一次慢提取阻塞所有后续调用；
2. ``notifications/cancelled`` 是 ``pass``，取消被忽略；
3. protocolVersion 硬编码，不协商。

实测并发差异（慢提取进行中再调零网络的预筛）：
    新实现 13.2ms ｜ 旧实现 2919.1ms

这里锁住三件事：工具面不变、参数搬运不覆盖默认值、结果与旧实现一致。
真正的"并发能力"由 SDK 的线程池保证，属集成性质，用
``tests/test_real_network.py`` 之外的手工探针验证（见交付报告）。
"""

from __future__ import annotations

from src.mcp import modern_server
from src.mcp.server import MCPServer as LegacyCore

# 迁移前旧实现的工具面（2026-11-22 实测导出），新增/删除工具应当是有意为之
_LEGACY_TOOL_NAMES = {
    "videomind_process",
    "videomind_download",
    "videomind_transcribe",
    "videomind_supported",
    "extract_video",
    "smart_extract",
    "prescreen_video",
    "archive_extract",
    "list_extractors",
    "videomind_capabilities",
    "videomind_config",
    "configure",
}


def _tools() -> dict:
    return modern_server.build_server()._tool_manager._tools


def test_tool_surface_matches_legacy():
    """工具名必须与迁移前完全一致——否则客户端的调用会静默失效。"""
    assert set(_tools()) == _LEGACY_TOOL_NAMES


def test_args_helper_drops_none_only():
    """``_args`` 只能丢掉 None。

    旧实现用 ``args.get("x", default)``：若把 ``"x": None`` 传进去会**覆盖默认值**，
    行为就变了。这是搬运层最容易出的错，单独锁住。
    """
    assert modern_server._args(a=1, b=None, c="") == {"a": 1, "c": ""}
    assert modern_server._args() == {}


def test_extract_video_passes_default_cost_tier_and_omits_unset():
    """extract_video 的默认 cost_tier 应显式传递；未提供的可选参数不得出现。"""
    captured: dict = {}
    original = modern_server._CORE._call_extract_video
    modern_server._CORE._call_extract_video = lambda args: captured.update(args) or {}
    try:
        _tools()["extract_video"].fn(url="https://example.com/v")
    finally:
        modern_server._CORE._call_extract_video = original

    assert captured["url"] == "https://example.com/v"
    assert captured["cost_tier"] == "cheap", "默认成本档必须显式传下去"
    assert "asr" not in captured and "asr_chain" not in captured


def test_supported_tool_result_matches_legacy():
    """纯函数类工具，新旧实现结果必须一致（防止搬运时丢字段）。"""
    legacy = LegacyCore()._call_supported({"url": "https://www.bilibili.com/video/BV1x"})
    modern = _tools()["videomind_supported"].fn(url="https://www.bilibili.com/video/BV1x")
    assert modern == legacy


def test_list_extractors_result_matches_legacy():
    legacy = LegacyCore()._call_list_extractors({})
    modern = _tools()["list_extractors"].fn()
    assert modern == legacy


def test_entry_point_defaults_to_modern_and_keeps_legacy_escape_hatch(monkeypatch):
    """``server.main()`` 默认走新实现；VMB_MCP_LEGACY=1 时退回旧实现。"""
    import src.mcp.server as legacy_module

    calls: list[str] = []
    monkeypatch.setattr(
        modern_server, "main", lambda: calls.append("modern")
    )

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
