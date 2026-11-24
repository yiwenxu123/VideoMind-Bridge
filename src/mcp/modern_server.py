"""MCP Server —— 薄适配器：默认把请求转给本机 REST 服务(:8787)。

## 为什么是"薄"

架构文档 §3.4/§8.2：**插件/MCP 是适配器，不是能力本体**；反模式是"插件即小应用"。
此前 MCP 在**进程内跑整套引擎**，直接造成三个问题（审查报告 §问题 4）：

1. **指标看不见 Agent 流量**——`/metrics` 只统计 pm2 那个 REST 进程。实测：通过 MCP
   提取一次，REST 的 `total` 一点没动。刚建的观测能力对 Agent 这条路完全失效。
2. 缓存/熔断/模型实例都是两份，行为可能与 REST 不一致。
3. 违反 §3.4 的分层约定。

现在默认薄适配器：MCP 只做参数翻译 → HTTP → 返回。引擎只有 pm2 那一个实例，
指标、缓存、熔断、限流天然统一。

`VMB_MCP_EMBEDDED=1` 可退回"进程内引擎"模式（服务没起时的兜底，或离线调试）。

## 工具面：3 个（2026-11-23 从 12 个收敛）

`extract` / `capabilities` / `comments`。收敛依据见 `docs/CONSUMERS.md` 与审查报告：
下游只用 extract / capabilities(+comments)；12 个工具定义 ≈1847 token 每轮都在上下文里。

## 兼容

入口仍是 `python -m src.mcp.server`（`server.main()` 转调本模块）；
`VMB_MCP_LEGACY=1` 退回手写 JSON-RPC 版（12 个旧工具）。
"""

from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
from pydantic import Field

DEFAULT_BASE_URL = "http://127.0.0.1:8787"
CONSUMER_ID = "dsh-mcp"
# 提取可能 40~200 秒；MCP 侧 toolCallTimeoutMs 已放宽到 600s，这里留出余量。
_TIMEOUT = httpx.Timeout(connect=5.0, read=540.0, write=15.0, pool=15.0)


def _base_url() -> str:
    return os.getenv("VMB_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _headers() -> dict[str, str]:
    headers = {"X-Consumer-Id": CONSUMER_ID}
    token = os.getenv("VIDEOMIND_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict:
    """调本机 REST。连接失败时给出**可执行**的提示，而不是裸 traceback。"""
    url = f"{_base_url()}{path}"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            response = client.request(method, url, json=payload, headers=_headers())
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"无法连接 VideoMind 服务 ({_base_url()})：{exc}\n"
            f"请先启动服务：pm2 start videomind-api（或 pm2 list 检查状态），"
            f"例如 curl {_base_url()}/health 验证。"
        ) from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"请求 {path} 超时：{exc}") from exc

    if response.status_code >= 400:
        raise RuntimeError(
            f"{path} 返回 HTTP {response.status_code}：{response.text[:300]}"
        )
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} 返回了非对象响应：{type(data).__name__}")
    return data


def _build_remote():
    """默认：薄适配器，全部转发给本机 REST。"""
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer("VideoMind Bridge", version="3.0.0")

    @mcp.tool(
        name="extract",
        description=(
            "从视频/笔记链接提取文字内容。"
            "mode=auto 执行提取；mode=prescreen 只做零网络的成本/价值预筛（不下载）。"
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
            str, Field(description="成本上限：free / cheap / paid / expensive / premium")
        ] = "cheap",
        asr_language: Annotated[str | None, Field(description="ASR 语言提示，如 zh")] = None,
    ) -> dict:
        if mode == "prescreen":
            return _request("POST", "/api/v1/prescreen", {"url": url, "mode": "quick"})
        if mode != "auto":
            raise ValueError(f"mode 只支持 auto / prescreen，收到 {mode!r}")
        payload: dict[str, Any] = {"url": url, "cost_tier": cost_tier}
        if asr_language:
            payload["asr_options"] = {"language": asr_language}
        return _request("POST", "/api/v1/extract", payload)

    @mcp.tool(
        name="capabilities",
        description=(
            "能力矩阵：哪些平台/提取器可用、ASR 后端与模型、支持哪些导出目标。"
            "注意提取器的 available 是**乐观可用性**（有凭证/二进制即 true），不代表链路当前通。"
        ),
    )
    def capabilities() -> dict:
        return _request("GET", "/api/v1/capabilities")

    @mcp.tool(
        name="comments",
        description="采集笔记/视频的评论（需要 VMB_ENABLE_COMMENTS=1）",
    )
    def comments(
        url: Annotated[str, Field(description="视频或笔记链接")],
        limit: Annotated[int, Field(description="评论条数上限")] = 20,
        sort: Annotated[str, Field(description="hot / time")] = "hot",
    ) -> dict:
        return _request(
            "POST", "/api/v1/comments", {"url": url, "limit": limit, "sort": sort}
        )

    return mcp


def build_server():
    """构建 MCP server（唯一形态：薄适配器）。"""
    return _build_remote()


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
