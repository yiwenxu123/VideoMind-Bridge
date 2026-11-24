#!/usr/bin/env python3
"""VideoMind Bridge 入口文件

两种启动模式（2026-11-24 起桌面 GUI 已下线，不再有隐式默认模式）：
1. API 服务：--api（默认 127.0.0.1:8787）
2. MCP Server：--mcp（stdio，供 AI Agent 调用）

使用方式：
    python main.py --api              # 启动 API 服务
    python main.py --api --port 9000  # 指定端口
    python main.py --mcp              # 启动 MCP Server

不带参数时打印用法并以退出码 2 结束。
"""

import argparse
import sys


def run_api(host: str = "127.0.0.1", port: int = 8787) -> None:
    """启动 API 服务"""
    import asyncio

    from src.api.server import APIServer

    server = APIServer(host=host, port=port)

    async def start():
        await server.start()

    try:
        asyncio.run(start())
    except KeyboardInterrupt:
        print("\nAPI 服务已停止")


def run_mcp() -> None:
    """启动 MCP Server（适用于 AI Agent 集成）"""
    from src.mcp.server import main as mcp_main
    mcp_main()


def main() -> int:
    """主入口"""
    parser = argparse.ArgumentParser(
        description="VideoMind Bridge - 智能视频处理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python main.py --api              启动 API 服务（默认端口 8787）
    python main.py --api --port 9000  启动 API 服务并指定端口
    python main.py --mcp              启动 MCP Server（AI Agent 集成）
        """
    )

    parser.add_argument(
        "--api",
        action="store_true",
        help="启动 API 服务模式"
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="启动 MCP Server（用于 AI Agent 集成）"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="API 服务监听地址（默认: 127.0.0.1）"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8787,
        help="API 服务监听端口（默认: 8787）"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="VideoMind Bridge 3.0.0"
    )

    args = parser.parse_args()

    if args.api:
        print(f"启动 API 服务: http://{args.host}:{args.port}")
        run_api(host=args.host, port=args.port)
        return 0
    elif args.mcp:
        # 2026-11-20 P0: stdio 模式下 stdout 是 MCP 协议流（换行分隔 JSON-RPC），
        # 任何非 JSON 文本都会让客户端在第一行解析失败。这行原来是 print() 到 stdout，
        # 而 README 推荐的正是 `python main.py --mcp`，属于必踩的坑。
        print(
            "启动 MCP Server（用于 AI Agent 集成，通过 stdio 通信）",
            file=sys.stderr,
        )
        run_mcp()
        return 0
    else:
        # 2026-11-24：桌面 GUI 已下线。不带参数时不再隐式启动任何模式，
        # 否则「敲错命令」会被当成「启动成功」，排查成本比多敲一个 --api 高得多。
        parser.print_usage(sys.stderr)
        print(
            "\n请显式选择模式：\n"
            "  python main.py --api    # 本地 API 服务（http://127.0.0.1:8787）\n"
            "  python main.py --mcp    # MCP Server（stdio，供 AI Agent 调用）\n"
            "桌面 GUI 与 v1 工作站（/legacy、/ws、/api/v1/tasks*）已于 2026-11-25 移除；"
            "现在只有 API 与 MCP 两种模式。",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
