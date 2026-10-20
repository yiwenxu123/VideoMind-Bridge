"""媒体获取类型（阶段 3）

把“从哪里拿媒体”从平台提取器里拆出来：提取器只负责解析 URL /
签名 / 候选直链，实际下载交给 MediaFetcher。这样换下载实现（httpx、
yt-dlp、未来的其他下载器）不需要改平台解析逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


class MediaFetchError(Exception):
    """媒体获取失败基类"""

    code = "media_fetch_error"


class MediaTooLarge(MediaFetchError):
    """超过大小上限"""

    code = "media_too_large"


class MediaFetchFailed(MediaFetchError):
    """网络/HTTP/子进程等执行失败"""

    code = "media_fetch_failed"


class MediaTranscodeError(MediaFetchError):
    """ffmpeg 转码失败"""

    code = "media_transcode_failed"


@dataclass
class MediaFetchRequest:
    """一次下载请求"""

    url: str
    dest: Path
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float = 300.0
    max_bytes: int = 300 * 1024 * 1024
    min_bytes: int = 1000


@dataclass
class FetchedMedia:
    """下载结果"""

    path: Path
    size: int
    content_type: str = ""
    source: str = ""
