#!/usr/bin/env python3
"""VideoMind Bridge 入口文件"""

import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.app import VideoMindApp


def main():
    """主入口"""
    app = VideoMindApp()
    app.initialize()
    
    # TODO: 启动 UI 或 CLI
    print("VideoMind Bridge 启动成功")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
