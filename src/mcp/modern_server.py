"""MCP Server —— mcp 2.x (``MCPServer``) 实现。

## 为什么要换掉手写 JSON-RPC 版

原实现（``src/mcp/server.py`` 的 ``MCPServer`` 类）能用，但有三个**功能性**缺陷：

1. **单线程阻塞**：主循环是 ``for line in sys.stdin``，一次 40~200 秒的提取会
   把之后所有请求排队——包括本应 <2ms 的 ``prescreen_video``。
2. **取消被忽略**：``notifications/cancelled`` 分支是 ``pass``。
3. **协议版本硬编码** ``2025-03-26``，不读客户端请求的版本、不协商。

``mcp>=2.3`` 的 ``MCPServer``（v2 起 FastMCP 改名而来）把**同步工具函数放进
anyio 线程池**执行（``utilities/func_metadata.py`` 用 ``anyio.to_thread.run_sync``），
因此上面的 1、2 自然解决，协议协商与 ``structuredContent`` 也由 SDK 负责。

## 兼容性策略

- **工具名、参数、返回结构与旧实现保持一一对应**，业务逻辑**完全复用**
  `server.MCPServer` 的 ``_call_*`` 方法——不重写，便于新旧逐项比对。
- 入口仍是 ``python -m src.mcp.server``（``server.main`` 转调本模块），
  所以 MCP 客户端配置**不需要改**。
- 设 ``VMB_MCP_LEGACY=1`` 可退回旧实现做对照。
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

    # ── v2 提取引擎（推荐）──────────────────────────────────────────────

    @mcp.tool(name="extract_video", description="提取视频/图文内容的完整文字")
    def extract_video(
        url: Annotated[str, Field(description="视频或笔记链接")],
        cost_tier: Annotated[
            str | None,
            Field(description="free / cheap / paid / expensive / premium"),
        ] = "cheap",
        asr: Annotated[str | None, Field(description="首选 ASR 后端")] = None,
        asr_chain: Annotated[list[str] | None, Field(description="严格 ASR 降级链")] = None,
        asr_language: Annotated[str | None, Field(description="ASR 语言提示")] = None,
    ) -> dict:
        return _CORE._call_extract_video(
            _args(
                url=url,
                cost_tier=cost_tier,
                asr=asr,
                asr_chain=asr_chain,
                asr_language=asr_language,
            )
        )

    @mcp.tool(name="smart_extract", description="先预筛再按需提取")
    def smart_extract(
        url: Annotated[str, Field(description="视频或笔记链接")],
        max_cost: Annotated[str | None, Field(description="成本上限")] = None,
        min_grade: Annotated[str, Field(description="最低可接受等级 S/A/B/C/D")] = "C",
    ) -> dict:
        return _CORE._call_smart_extract(
            _args(url=url, max_cost=max_cost, min_grade=min_grade)
        )

    @mcp.tool(name="prescreen_video", description="纯规则预筛评分（零网络）")
    def prescreen_video(
        url: Annotated[str, Field(description="视频或笔记链接")],
        mode: Annotated[str, Field(description="quick(<2ms) 或 full(<10s)")] = "quick",
    ) -> dict:
        return _CORE._call_prescreen_video(_args(url=url, mode=mode))

    @mcp.tool(name="archive_extract", description="提取并归档到 Obsidian / 本地")
    def archive_extract(
        url: Annotated[str, Field(description="视频或笔记链接")],
        targets: Annotated[list[str] | None, Field(description="obsidian,local")] = None,
        obsidian_vault: Annotated[str | None, Field(description="Obsidian vault 路径")] = None,
        obsidian_subfolder: Annotated[str | None, Field(description="子目录")] = None,
        local_output: Annotated[str | None, Field(description="本地输出目录")] = None,
    ) -> dict:
        return _CORE._call_archive_extract(
            _args(
                url=url,
                targets=targets,
                obsidian_vault=obsidian_vault,
                obsidian_subfolder=obsidian_subfolder,
                local_output=local_output,
            )
        )

    @mcp.tool(name="list_extractors", description="提取器清单（乐观可用性，不代表链路通）")
    def list_extractors() -> dict:
        return _CORE._call_list_extractors({})

    @mcp.tool(name="videomind_capabilities", description="ASR 后端与提取器能力矩阵")
    def videomind_capabilities() -> dict:
        return _CORE._call_capabilities({})

    @mcp.tool(name="videomind_config", description="查看当前配置")
    def videomind_config() -> dict:
        return _CORE._call_config({})

    @mcp.tool(name="configure", description="修改配置（action=set/unset/list）")
    def configure(
        action: Annotated[str, Field(description="set / unset / list")],
        key: Annotated[str | None, Field(description="配置键")] = None,
        value: Annotated[str | None, Field(description="配置值")] = None,
    ) -> dict:
        return _CORE._call_configure(_args(action=action, key=key, value=value))

    # ── v1 遗留（已标 DEPRECATED，保留仅为兼容旧调用方）────────────────

    @mcp.tool(
        name="videomind_process",
        description="[DEPRECATED] 完整处理：下载→转录→AI摘要→导出（v1）",
    )
    def videomind_process(
        url: Annotated[str, Field(description="视频链接或本地媒体文件")],
        mode: Annotated[str, Field(description="full / download / transcribe")] = "full",
        targets: Annotated[list[str] | None, Field(description="导出目标")] = None,
        whisper_model: Annotated[str | None, Field(description="tiny/base/small/medium")] = None,
        cookie_browser: Annotated[str | None, Field(description="chrome/edge/firefox")] = None,
    ) -> dict:
        return _CORE._call_process(
            _args(
                url=url,
                mode=mode,
                targets=targets,
                whisper_model=whisper_model,
                cookie_browser=cookie_browser,
            )
        )

    @mcp.tool(name="videomind_download", description="[DEPRECATED] 仅下载视频/音频")
    def videomind_download(
        url: Annotated[str, Field(description="视频链接或本地媒体文件")],
        keep_video: Annotated[bool, Field(description="是否保留视频文件")] = True,
        cookie_browser: Annotated[str | None, Field(description="chrome/edge/firefox")] = None,
    ) -> dict:
        return _CORE._call_download(
            _args(url=url, keep_video=keep_video, cookie_browser=cookie_browser)
        )

    @mcp.tool(name="videomind_transcribe", description="[DEPRECATED] 仅转录音频生成 SRT")
    def videomind_transcribe(
        audio_path: Annotated[str, Field(description="音频文件路径")],
        whisper_model: Annotated[str | None, Field(description="模型大小")] = None,
        language: Annotated[str | None, Field(description="语言代码")] = None,
    ) -> dict:
        return _CORE._call_transcribe(
            _args(audio_path=audio_path, whisper_model=whisper_model, language=language)
        )

    @mcp.tool(name="videomind_supported", description="检查链接是否为支持的平台")
    def videomind_supported(url: Annotated[str, Field(description="待检查链接")]) -> dict:
        return _CORE._call_supported(_args(url=url))

    return mcp


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
