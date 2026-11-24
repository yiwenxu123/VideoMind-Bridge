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

# 2026-11-23 收敛后的工具面：3 个。
# 从 12 个砍到 3 个是有意为之，依据见 docs/CONSUMERS.md 与审查报告 §问题 3：
# - 下游只用 extract / capabilities（+ comments），其余 10 个无已知消费者；
# - 12 个工具 ≈1847 token，每轮都在上下文里；
# - prescreen/smart/supported 是 extract 的参数或成本闸，不该各占一个工具；
# - configure/videomind_config 属配置写入，不该暴露给模型（最小权限）；
# - v1 的 process/download/transcribe 已 DEPRECATED；archive 属上层 Skill 职责。
_TOOL_NAMES = {"extract", "capabilities", "comments"}


def _tools() -> dict:
    return modern_server.build_server()._tool_manager._tools


def test_tool_surface_is_the_agreed_three():
    """工具面固定在 3 个：增删必须是有意为之（并同步更新本文与 CONTRACT）。"""
    assert set(_tools()) == _TOOL_NAMES


def test_args_helper_drops_none_only():
    """``_args`` 只能丢掉 None。

    旧实现用 ``args.get("x", default)``：若把 ``"x": None`` 传进去会**覆盖默认值**，
    行为就变了。这是搬运层最容易出的错，单独锁住。
    """
    assert modern_server._args(a=1, b=None, c="") == {"a": 1, "c": ""}
    assert modern_server._args() == {}


def test_extract_passes_default_cost_tier_and_omits_unset():
    """extract_video 的默认 cost_tier 应显式传递；未提供的可选参数不得出现。"""
    captured: dict = {}
    original = modern_server._CORE._call_extract_video
    modern_server._CORE._call_extract_video = lambda args: captured.update(args) or {}
    try:
        _tools()["extract"].fn(url="https://example.com/v")
    finally:
        modern_server._CORE._call_extract_video = original

    assert captured["url"] == "https://example.com/v"
    assert captured["cost_tier"] == "cheap", "默认成本档必须显式传下去"
    assert "asr" not in captured and "asr_chain" not in captured


def test_capabilities_result_matches_legacy():
    """纯函数类工具，新旧实现结果必须一致（防止搬运时丢字段）。"""
    legacy = LegacyCore()._call_capabilities({})
    modern = _tools()["capabilities"].fn()
    assert modern == legacy


def test_prescreen_merged_into_extract():
    """prescreen 不再是独立工具，改由 extract(mode="prescreen") 提供。"""
    legacy = LegacyCore()._call_prescreen_video(
        {"url": "https://www.bilibili.com/video/BV1x", "mode": "quick"}
    )
    modern = _tools()["extract"].fn(
        url="https://www.bilibili.com/video/BV1x", mode="prescreen"
    )
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
