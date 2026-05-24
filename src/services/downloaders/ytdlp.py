"""yt-dlp 下载器实现

基于 yt-dlp 的视频下载器，支持国际平台。
"""

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Set
from urllib.parse import urlparse

import yt_dlp

from .base import (
    DownloaderBase,
    DownloaderCapability,
    DownloaderInfo,
    DownloadOptions,
    DownloadResult,
    ProgressCallback,
)
from ...models.task import VideoMetadata
from ...utils import get_logger, sanitize_filename
from ...utils.exceptions import DownloadError

logger = get_logger(__name__)


class YtdlpDownloader(DownloaderBase):
    """yt-dlp 下载器

    支持平台：YouTube, Bilibili, TikTok, Douyin, XiaoHongShu 等。
    """

    SUPPORTED_PLATFORMS: Set[str] = {
        "youtube", "bilibili", "tiktok", "twitter", "instagram",
        "facebook", "vimeo", "reddit", "weibo", "zhihu",
        "douyin", "xiaohongshu",
    }
    
    def __init__(self):
        self._ytdlp_version: Optional[str] = None
    
    @property
    def info(self) -> DownloaderInfo:
        return DownloaderInfo(
            name="yt-dlp",
            version=self._get_version(),
            platforms=self.SUPPORTED_PLATFORMS,
            capabilities={
                DownloaderCapability.VIDEO,
                DownloaderCapability.AUDIO_ONLY,
                DownloaderCapability.METADATA,
                DownloaderCapability.PLAYLIST,
                DownloaderCapability.SUBTITLE,
                DownloaderCapability.THUMBNAIL,
            },
            priority=100,
            description="基于 yt-dlp 的下载器，支持国际平台及国内平台（抖音/小红书）",
        )
    
    @property
    def is_available(self) -> bool:
        try:
            import yt_dlp
            return True
        except ImportError:
            return False
    
    def _get_version(self) -> str:
        if self._ytdlp_version is None:
            try:
                self._ytdlp_version = yt_dlp.version.__version__
            except AttributeError:
                self._ytdlp_version = "unknown"
        return self._ytdlp_version
    
    def can_handle(self, url: str) -> bool:
        platform = self._detect_platform(url)
        return platform in self.SUPPORTED_PLATFORMS or platform == "unknown"
    
    def download(
        self,
        url: str,
        options: DownloadOptions,
        progress_callback: Optional[ProgressCallback] = None
    ) -> DownloadResult:
        logger.info(f"yt-dlp 开始下载: {url}")
        
        try:
            options.output_dir.mkdir(parents=True, exist_ok=True)
            
            date_str = datetime.now().strftime("%Y-%m-%d")
            temp_dir = options.output_dir / date_str / ".temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            ytdlp_opts = self._build_options(options, temp_dir, progress_callback)
            
            with yt_dlp.YoutubeDL(ytdlp_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if not info:
                    return DownloadResult(
                        success=False,
                        error_message="无法获取视频信息",
                        error_code="EXTRACT_FAILED"
                    )
                
                return self._process_result(info, options, temp_dir)
                
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            logger.error(f"yt-dlp 下载失败: {error_msg}")
            
            if "HTTP Error 404" in error_msg or "Video unavailable" in error_msg:
                error_code = "VIDEO_NOT_FOUND"
            elif "Private video" in error_msg:
                error_code = "PRIVATE_VIDEO"
            elif "Sign in" in error_msg or "login" in error_msg.lower():
                error_code = "LOGIN_REQUIRED"
            else:
                error_code = "DOWNLOAD_FAILED"
            
            return DownloadResult(
                success=False,
                error_message=error_msg,
                error_code=error_code
            )
        except Exception as e:
            logger.error(f"yt-dlp 下载异常: {e}")
            return DownloadResult(
                success=False,
                error_message=str(e),
                error_code="UNKNOWN_ERROR"
            )
    
    def get_metadata(self, url: str) -> Optional[VideoMetadata]:
        try:
            opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,
            }
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    return None
                
                return VideoMetadata(
                    title=info.get("title", "未知标题"),
                    author=info.get("uploader", "未知作者"),
                    duration=info.get("duration", 0),
                    platform=self._detect_platform(url),
                    url=url,
                    thumbnail_url=info.get("thumbnail"),
                    description=info.get("description", ""),
                )
        except Exception as e:
            logger.error(f"获取元数据失败: {e}")
            return None
    
    def _build_options(
        self,
        options: DownloadOptions,
        temp_dir: Path,
        progress_callback: Optional[ProgressCallback]
    ) -> dict:
        if options.keep_video:
            format_spec = f"bestvideo[ext={options.video_format}]+bestaudio[ext={options.audio_format}]/best"
        else:
            format_spec = f"bestaudio[ext={options.audio_format}]/bestaudio/best"
        
        outtmpl = str(temp_dir / "%(title).100s.%(ext)s")
        
        opts: dict[str, Any] = {
            "format": format_spec,
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "overwrites": True,
            "writesubtitles": bool(options.subtitle_languages),
            "subtitleslangs": options.subtitle_languages or ["all"],
            "writethumbnail": False,
            "postprocessors": [],
        }
        
        if not options.keep_video:
            opts["postprocessors"].append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": options.audio_format,
                "preferredquality": options.audio_quality,
            })
        
        if options.cookies:
            opts["cookiefile"] = options.cookies
        elif options.cookies_file:
            opts["cookiefile"] = str(options.cookies_file)
        elif options.cookies_from_browser:
            opts["cookiesfrombrowser"] = (options.cookies_from_browser,)

        if options.proxy:
            opts["proxy"] = options.proxy
        
        if progress_callback:
            opts["progress_hooks"] = [
                lambda d: self._progress_hook(d, progress_callback)
            ]
        
        return opts
    
    def _progress_hook(self, data: dict, callback: ProgressCallback) -> None:
        status = data.get("status")
        
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate", 0)
            downloaded = data.get("downloaded_bytes", 0)
            
            if total > 0:
                percent = (downloaded / total) * 100
                callback("下载中", percent)
            else:
                callback("下载中", 0)
        elif status == "finished":
            callback("处理中", 100)
    
    def _process_result(
        self,
        info: dict,
        options: DownloadOptions,
        temp_dir: Path
    ) -> DownloadResult:
        title = info.get("title", "未知标题")
        safe_title = sanitize_filename(title)
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        output_dir = options.output_dir / date_str / safe_title
        output_dir.mkdir(parents=True, exist_ok=True)
        
        ext = options.audio_format if not options.keep_video else options.video_format
        expected_file = temp_dir / f"{safe_title}.{ext}"
        
        downloaded_files = list(temp_dir.glob(f"{safe_title}.*"))
        if not downloaded_files:
            downloaded_files = list(temp_dir.glob("*"))
        
        audio_path: Optional[Path] = None
        video_path: Optional[Path] = None
        
        for file_path in downloaded_files:
            if file_path.is_file():
                target_path = output_dir / file_path.name
                
                import shutil
                shutil.move(str(file_path), str(target_path))
                
                if file_path.suffix.lower() in [".m4a", ".mp3", ".opus", ".webm"]:
                    if audio_path is None:
                        audio_path = target_path
                elif file_path.suffix.lower() in [".mp4", ".mkv", ".webm", ".avi"]:
                    if video_path is None:
                        video_path = target_path
        
        metadata = VideoMetadata(
            title=title,
            author=info.get("uploader", "未知作者"),
            duration=info.get("duration", 0),
            platform=self._detect_platform(info.get("webpage_url", "")),
            url=info.get("webpage_url", ""),
            thumbnail_url=info.get("thumbnail"),
            description=info.get("description", ""),
        )
        
        import shutil
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
        
        logger.info(f"yt-dlp 下载完成: {title}")
        
        return DownloadResult(
            success=True,
            audio_path=audio_path,
            video_path=video_path,
            metadata=metadata,
        )
