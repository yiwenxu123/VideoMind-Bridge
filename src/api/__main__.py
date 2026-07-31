"""API服务启动入口

用法:
    python -m src.api
    python -m src.api --host 127.0.0.1 --port 8080

安全提示:
    默认仅监听 127.0.0.1 (本地回环), 不要在生产/公网环境绑定 0.0.0.0。
    如需远程访问, 请先设置环境变量 VIDEOMIND_API_TOKEN 开启鉴权。
"""

import argparse
import asyncio
import sys

from .server import APIServer


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="VideoMind Bridge API Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 默认启动 (127.0.0.1:8787)
  python -m src.api

  # 指定主机和端口
  python -m src.api --host 127.0.0.1 --port 8080

  # 查看帮助
  python -m src.api --help

安全提示:
  默认绑定 127.0.0.1 (仅本机访问)。
  切勿在公网绑定 0.0.0.0; 若确有远程访问需求,
  请先设置环境变量 VIDEOMIND_API_TOKEN 开启 Bearer 鉴权。
        """
    )

    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="监听地址 (默认: 127.0.0.1)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8787,
        help="监听端口 (默认: 8787)",
    )

    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                VideoMind Bridge API Server                   ║
╠══════════════════════════════════════════════════════════════╣
║  版本: 3.0.0                                                 ║
║  地址: http://{args.host}:{args.port:<5}                            ║
║  文档: http://{args.host}:{args.port}/docs                          ║
╚══════════════════════════════════════════════════════════════╝
    """)

    server = APIServer(host=args.host, port=args.port)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n正在关闭服务器...")
        sys.exit(0)


if __name__ == "__main__":
    main()
