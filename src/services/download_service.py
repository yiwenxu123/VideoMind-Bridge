"""下载服务实现

使用下载器路由自动选择最佳下载器。
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..models.task import VideoMetadata
from ..utils import get_logger
from ..utils.exceptions import DownloadError, UnsupportedPlatformError
from ..utils.platform_detector import detect_platform as _detect_platform_impl
from .downloaders import DownloaderRouter, DownloadOptions

logger = get_logger(__name__)

ProgressCallback = Callable[[str, float], None]


@dataclass
class DownloadResult:
    """下载结果"""
    video_path: Path | None
    audio_path: Path
    metadata: VideoMetadata


class DownloadService:
    """视频下载服务
    
    使用 yt-dlp 下载器支持 YouTube、Bilibili、抖音、小红书等多平台。
    """

    MAX_RETRIES = 3
    RETRY_DELAY = 1.0
    RETRY_BACKOFF = 2.0

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._router = DownloaderRouter()

    def download(
        self,
        url: str,
        download_video: bool = True,
        video_quality: str = "best",
        progress_callback: ProgressCallback | None = None,
        cookies_from_browser: str | None = None,
    ) -> DownloadResult:
        """
        下载视频和/或音频（带重试机制）

        Args:
            url: 视频链接
            download_video: True 时下载完整视频，False 时仅下载音频
            video_quality: 视频质量 (best/worst/720p/1080p等)
            progress_callback: 进度回调函数 (status, percent) -> None
            cookies_from_browser: 从浏览器读取 cookies（chrome/safari/firefox）

        Returns:
            DownloadResult: 下载结果

        Raises:
            DownloadError: 下载失败时抛出
        """
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                return self._do_download(
                    url, download_video, video_quality, progress_callback,
                    cookies_from_browser=cookies_from_browser,
                )
            except UnsupportedPlatformError:
                raise
            except DownloadError as e:
                if e.error_code in ["VIDEO_NOT_FOUND", "AGE_RESTRICTED", "REGION_BLOCKED", "PRIVATE_VIDEO"]:
                    raise

                last_error = e

                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAY * (self.RETRY_BACKOFF ** attempt)
                    logger.warning(f"下载失败（尝试 {attempt + 1}/{self.MAX_RETRIES}）: {e}，{delay:.1f}秒后重试...")
                    if progress_callback:
                        progress_callback(f"下载失败，{delay:.1f}秒后重试...", 0)
                    time.sleep(delay)
                else:
                    logger.error(f"下载失败，已重试 {self.MAX_RETRIES} 次: {e}")

        raise DownloadError(
            f"下载失败，已重试 {self.MAX_RETRIES} 次: {last_error}",
            error_code="DOWNLOAD_FAILED",
            details={"url": url, "retries": self.MAX_RETRIES}
        ) from last_error

    def _do_download(
        self,
        url: str,
        download_video: bool,
        video_quality: str,
        progress_callback: ProgressCallback | None,
        cookies_from_browser: str | None = None,
    ) -> DownloadResult:
        """实际执行下载"""

        if progress_callback:
            progress_callback("正在选择下载器...", 2)

        options = DownloadOptions(
            output_dir=self.output_dir,
            keep_video=download_video,
            video_quality=video_quality,
            cookies_from_browser=cookies_from_browser,
        )

        result = self._router.download(url, options, progress_callback)

        if not result.success:
            raise DownloadError(
                result.error_message or "下载失败",
                error_code=result.error_code or "DOWNLOAD_FAILED",
                details={"url": url}
            )

        audio_path = result.audio_path
        if audio_path is None:
            raise DownloadError(
                "下载完成但未找到音频文件",
                error_code="FILE_NOT_FOUND",
                details={"url": url}
            )

        if result.metadata is None:
            result.metadata = VideoMetadata(
                title="未知标题",
                author="未知作者",
                duration=0,
                platform=self._detect_platform(url),
                url=url,
            )

        return DownloadResult(
            video_path=result.video_path,
            audio_path=audio_path,
            metadata=result.metadata,
        )

    def get_supported_platforms(self) -> list[str]:
        """获取支持的平台列表"""
        return self._router.get_supported_platforms()

    def is_supported(self, url: str) -> bool:
        """检查是否支持该 URL"""
        return self._router.is_supported(url)

    def get_metadata(self, url: str) -> VideoMetadata | None:
        """获取视频元数据（不下载）"""
        return self._router.get_metadata(url)

    def list_downloaders(self) -> list[dict]:
        """列出所有可用的下载器"""
        return self._router.list_downloaders()

    def _detect_platform(self, url: str) -> str:
        """检测视频平台"""
        return _detect_platform_impl(url)
