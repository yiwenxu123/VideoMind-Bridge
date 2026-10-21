"""兼容导入：通用 TTL 缓存已移到 src.core.cache。"""

from ..cache import TTLCache

__all__ = ["TTLCache"]
