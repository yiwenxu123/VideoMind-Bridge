"""下载器模块

提供多种视频下载器实现，支持不同平台。
"""

from .base import (
    DownloaderBase,
    DownloaderCapability,
    DownloaderInfo,
    DownloadOptions,
    DownloadResult,
)
from .router import DownloaderRouter
from .ytdlp import YtdlpDownloader

__all__ = [
    "DownloaderBase",
    "DownloaderCapability",
    "DownloaderInfo",
    "DownloadOptions",
    "DownloadResult",
    "YtdlpDownloader",
    "DownloaderRouter",
]
