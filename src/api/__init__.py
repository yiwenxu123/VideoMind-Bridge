"""本地API服务模块

提供REST API接口，支持外部工具集成。
（2026-11-25 A2：WebSocket 与 v1 任务接口已移除）
"""

from .models import APIError
from .server import APIServer

__all__ = [
    "APIServer",
    "APIError",
]
