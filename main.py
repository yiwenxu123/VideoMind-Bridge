#!/usr/bin/env python3
"""VideoMind Bridge 入口文件

支持两种启动模式：
1. GUI 模式（默认）：启动图形界面
2. CLI 模式：通过命令行参数启动 API 服务

使用方式：
    python main.py              # 启动 GUI
    python main.py --api        # 启动 API 服务
    python main.py --api --port 9000  # 指定端口
"""

import argparse
import sys


def run_gui() -> int:
    """启动 GUI 应用"""
    from src.gui.app import main as gui_main
    return gui_main()


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
    python main.py                    启动 GUI 界面
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
        print("启动 MCP Server（用于 AI Agent 集成，通过 stdio 通信）")
        run_mcp()
        return 0
    else:
        return run_gui()


if __name__ == "__main__":
    sys.exit(main())
