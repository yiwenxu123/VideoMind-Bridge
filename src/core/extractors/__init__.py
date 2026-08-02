"""内容提取器注册与工厂"""

from .base import ContentExtractor

# 提取器注册表
_extractors: dict[str, type[ContentExtractor]] = {}


def register_extractor(name: str, cls: type[ContentExtractor]) -> None:
    """注册提取器"""
    _extractors[name] = cls


def get_extractor(name: str) -> ContentExtractor | None:
    """获取指定名称的提取器实例"""
    cls = _extractors.get(name)
    if cls is None:
        return None
    return cls()


def list_extractors() -> list[str]:
    """列出所有注册的提取器名称"""
    return list(_extractors.keys())


def create_all_extractors() -> list[ContentExtractor]:
    """创建所有注册的提取器实例"""
    return [cls() for cls in _extractors.values()]


# 延迟导入以触发注册
from . import (
    aliyun_asr_extractor,  # noqa: E402, F811
    apify_extractor,  # noqa: E402, F811
    bilibili_extractor,  # noqa: E402, F811
    coze_extractor,  # noqa: E402, F811
    douyin_extractor,  # noqa: E402, F811
    tikhub_extractor,  # noqa: E402, F811
    xiaohongshu_extractor,  # noqa: E402, F811
    youtube_extractor,  # noqa: E402, F811
    ytdlp_asr_extractor,  # noqa: E402, F811
    ytdlp_extractor,  # noqa: E402, F811
)
