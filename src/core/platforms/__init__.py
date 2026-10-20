"""平台 API 客户端共享层。"""

from .bilibili_client import BilibiliApiError, BilibiliClient, load_cookie_header

__all__ = ["BilibiliApiError", "BilibiliClient", "load_cookie_header"]
