"""媒体获取与转码（阶段 3）

- HttpMediaFetcher: 直链流式下载（防盗链头、大小上限、失败清理）
- YtDlpMediaFetcher: yt-dlp 下载 + cookies + 元信息
- audio: 共享 ffmpeg 转码（mp3 / 16k wav）
"""

from .audio import find_ffmpeg, to_16k_mono_wav, transcode_to_mp3
from .http_fetcher import HttpMediaFetcher
from .types import (
    FetchedMedia,
    MediaFetchError,
    MediaFetchFailed,
    MediaFetchRequest,
    MediaTooLarge,
    MediaTranscodeError,
)
from .ytdlp_fetcher import YtDlpMediaFetcher, resolve_ytdlp

__all__ = [
    "FetchedMedia",
    "HttpMediaFetcher",
    "MediaFetchError",
    "MediaFetchFailed",
    "MediaFetchRequest",
    "MediaTooLarge",
    "MediaTranscodeError",
    "YtDlpMediaFetcher",
    "find_ffmpeg",
    "resolve_ytdlp",
    "to_16k_mono_wav",
    "transcode_to_mp3",
]
