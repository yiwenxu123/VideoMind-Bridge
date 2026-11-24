"""MCP Server 入口（stdio）

历史：这里曾经是一份手写的 JSON-RPC 实现，暴露 16 个工具（下载/转录/AI 摘要/导出）。
2026-11-24（P2）改为薄适配器后，真正的工具实现搬到了 ``src.mcp.modern_server``；
2026-11-25（A2）v1 流水线删除，旧实现与 ``VMB_MCP_LEGACY=1`` 开关一并移除。

保留这个模块名是硬约束：DSH 的 ``cordis.patch.yml`` 用 ``-m src.mcp.server`` 启动它
（换成 main.py 会往 stdout 打一行中文，破坏 stdio 的 JSON-RPC 流）。
"""

from __future__ import annotations


def main() -> None:
    """启动薄适配器 MCP server（工具经 HTTP 调用本机 REST :8787）。"""
    from src.mcp.modern_server import main as _modern_main

    _modern_main()


if __name__ == "__main__":
    main()
