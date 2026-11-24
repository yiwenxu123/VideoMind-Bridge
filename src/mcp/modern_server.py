"""MCP Server —— mcp 2.x (``MCPServer``) 实现。

## 为什么要换掉手写 JSON-RPC 版

原实现（``src/mcp/server.py`` 的 ``MCPServer`` 类）能用，但有三个**功能性**缺陷：

1. **单线程阻塞**：主循环是 ``for line in sys.stdin``，一次 40~200 秒的提取会
   把之后所有请求排队——包括本应 <2ms 的 ``prescreen_video``。
2. **取消被忽略**：``notifications/cancelled`` 分支是 ``pass``。
3. **协议版本硬编码** ``2025-03-26``，不读客户端请求的版本、不协商。

``mcp>=2.3`` 的 ``MCPServer`` 把**同步工具函数放进 anyio 线程池**执行
（``utilities/func_metadata.py`` 用 ``anyio.to_thread.run_sync``），
因此上面的 1、2 自然解决，协议协商与 ``structuredContent`` 也由 SDK 负责。

## 工具面：3 个（2026-11-23 收敛，原 12 个）

对外暴露的是**工作流**，不是内部端点。收敛依据：

- 下游实际只用 ``extract`` 与 ``capabilities``（`docs/CONSUMERS.md`），
  外加评论采集；其余 10 个工具**没有已知消费者**。
- 官方文档明确"工具越多不一定越好"：全部工具定义进上下文会
  "wastes tokens, increases latency, and degrades model performance"
  （MCP client best practices）。收敛前实测 12 个工具 ≈1847 token，**每轮都在上下文里**。
- 原则：同一工作流不拆多刀（``prescreen``/``smart``/``supported`` 都是 ``extract``
  的参数或成本闸）；配置类不暴露给模型（最小权限）；已 DEPRECATED 的 v1 工具移除。

被移除的能力**没有消失**：仍在 REST（``/api/v1/extract/archive``、``/api/v1/parse`` 等）、
CLI 与旧实现类里。需要时用 ``VMB_MCP_LEGACY=1`` 退回旧工具面。

## 兼容性

- 入口仍是 ``python -m src.mcp.server``（``server.main`` 转调本模块），客户端配置不用改。
- 业务逻辑**完全复用** ``server.MCPServer`` 的 ``_call_*``，不重写，便于新旧比对。
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from .server import MCPServer as _LegacyCore

# 业务逻辑的唯一实现。这里只做参数搬运，避免两份实现漂移。
_CORE = _LegacyCore()


def _args(**kwargs: Any) -> dict[str, Any]:
    """丢掉未提供(None)的参数。

    旧实现用 ``args.get("x", default)`` 取默认值，若把 ``"x": None`` 塞进去会**覆盖**
    默认值导致行为变化。所以这里只保留调用方真正给出的键。
    """
    return {k: v for k, v in kwargs.items() if v is not None}


def build_server():
    """构建并返回配置好全部工具的 MCPServer。"""
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer("VideoMind Bridge", version="3.0.0")

    @mcp.tool(
        name="extract",
        description=(
            "从视频/笔记链接提取文字内容。"
            "mode=auto 执行提取；mode=prescreen 只做零网络的成本/价值预筛（<2ms，不下载）。"
            "返回含 success / completeness / platform / content / source / error_code。"
            "注意：success=true 只表示拿到了东西，完整性看 completeness（meta 表示只有标题/文案）。"
        ),
    )
    def extract(
        url: Annotated[str, Field(description="视频或笔记链接")],
        mode: Annotated[
            str, Field(description="auto=执行提取；prescreen=只预筛（不下载）")
        ] = "auto",
        cost_tier: Annotated[
            str,
            Field(description="成本上限：free / cheap / paid / expensive / premium"),
        ] = "cheap",
        asr_language: Annotated[str | None, Field(description="ASR 语言提示，如 zh")] = None,
    ) -> dict:
        if mode == "prescreen":
            return _CORE._call_prescreen_video(_args(url=url, mode="quick"))
        if mode != "auto":
            raise ValueError(f"mode 只支持 auto / prescreen，收到 {mode!r}")
        return _CORE._call_extract_video(
            _args(url=url, cost_tier=cost_tier, asr_language=asr_language)
        )

    @mcp.tool(
        name="capabilities",
        description=(
            "能力矩阵：哪些平台/提取器可用、ASR 后端与模型、支持哪些导出目标。"
            "注意提取器的 available 是**乐观可用性**（有凭证/二进制即 true），不代表链路当前通。"
        ),
    )
    def capabilities() -> dict:
        return _CORE._call_capabilities({})

    @mcp.tool(
        name="comments",
        description="采集笔记/视频的评论（需要 VMB_ENABLE_COMMENTS=1）",
    )
    def comments(
        url: Annotated[str, Field(description="视频或笔记链接")],
        limit: Annotated[int, Field(description="评论条数上限")] = 20,
        sort: Annotated[str, Field(description="hot / time")] = "hot",
    ) -> dict:
        return _CORE._call_get_comments(_args(url=url, limit=limit, sort=sort))

    return mcp


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
