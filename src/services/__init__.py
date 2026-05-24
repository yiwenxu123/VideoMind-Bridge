"""服务层模块"""

from .interfaces import (
    AIServiceInterface,
    DownloadServiceInterface,
    ProgressCallback,
    TranscribeServiceInterface,
)

__all__ = [
    "DownloadServiceInterface",
    "TranscribeServiceInterface",
    "AIServiceInterface",
    "ProgressCallback",
]
