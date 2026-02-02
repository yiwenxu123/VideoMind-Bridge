"""服务层模块"""

from .interfaces import (
    DownloadServiceInterface,
    TranscribeServiceInterface,
    AIServiceInterface,
    ProgressCallback,
)

__all__ = [
    "DownloadServiceInterface",
    "TranscribeServiceInterface",
    "AIServiceInterface",
    "ProgressCallback",
]
