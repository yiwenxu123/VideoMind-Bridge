"""内容提取器注册与工厂"""

from typing import Dict, List, Optional, Type

from .base import ContentExtractor

# 提取器注册表
_extractors: Dict[str, Type[ContentExtractor]] = {}


def register_extractor(name: str, cls: Type[ContentExtractor]) -> None:
    """注册提取器"""
    _extractors[name] = cls


def get_extractor(name: str) -> Optional[ContentExtractor]:
    """获取指定名称的提取器实例"""
    cls = _extractors.get(name)
    if cls is None:
        return None
    return cls()


def list_extractors() -> List[str]:
    """列出所有注册的提取器名称"""
    return list(_extractors.keys())


def create_all_extractors() -> List[ContentExtractor]:
    """创建所有注册的提取器实例"""
    return [cls() for cls in _extractors.values()]


# 延迟导入以触发注册
from . import bilibili_extractor  # noqa: E402, F811
from . import youtube_extractor   # noqa: E402, F811
from . import ytdlp_extractor     # noqa: E402, F811
from . import coze_extractor      # noqa: E402, F811
from . import douyin_extractor    # noqa: E402, F811
from . import xiaohongshu_extractor  # noqa: E402, F811
