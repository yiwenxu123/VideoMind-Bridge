"""下载器路由

自动选择合适的下载器处理 URL。
"""


from ...models.task import VideoMetadata
from ...utils import get_logger
from ...utils.exceptions import UnsupportedPlatformError
from .base import (
    DownloaderBase,
    DownloadOptions,
    DownloadResult,
    ProgressCallback,
)
from .ytdlp import YtdlpDownloader

logger = get_logger(__name__)


class DownloaderRouter:
    """下载器路由

    自动选择合适的下载器处理 URL。
    支持按优先级和平台匹配选择下载器。
    """

    def __init__(self):
        self._downloaders: list[DownloaderBase] = []
        self._register_default_downloaders()

    def _register_default_downloaders(self) -> None:
        ytdlp = YtdlpDownloader()
        if ytdlp.is_available:
            self.register(ytdlp)

    def register(self, downloader: DownloaderBase) -> None:
        if not downloader.is_available:
            logger.warning(f"下载器 {downloader.info.name} 不可用，跳过注册")
            return

        self._downloaders.append(downloader)
        self._downloaders.sort(key=lambda d: d.info.priority)

        logger.info(
            f"注册下载器: {downloader.info.name} "
            f"(优先级: {downloader.info.priority}, "
            f"平台: {', '.join(downloader.info.platforms)})"
        )

    def unregister(self, name: str) -> bool:
        for i, downloader in enumerate(self._downloaders):
            if downloader.info.name == name:
                self._downloaders.pop(i)
                logger.info(f"注销下载器: {name}")
                return True
        return False

    def get_downloader(self, url: str) -> DownloaderBase | None:
        for downloader in self._downloaders:
            if downloader.can_handle(url):
                return downloader

        return None

    def download(
        self,
        url: str,
        options: DownloadOptions,
        progress_callback: ProgressCallback | None = None,
    ) -> DownloadResult:
        downloader = self.get_downloader(url)

        if not downloader:
            raise UnsupportedPlatformError(
                f"不支持的平台: {url}",
                error_code="UNSUPPORTED_PLATFORM",
                details={"url": url}
            )

        logger.info(f"使用 {downloader.info.name} 下载: {url}")

        return downloader.download(url, options, progress_callback)

    def get_metadata(self, url: str) -> VideoMetadata | None:
        downloader = self.get_downloader(url)

        if not downloader:
            return None

        return downloader.get_metadata(url)

    def is_supported(self, url: str) -> bool:
        return self.get_downloader(url) is not None

    def get_supported_platforms(self) -> list[str]:
        platforms = set()
        for downloader in self._downloaders:
            platforms.update(downloader.info.platforms)
        return sorted(platforms)

    def list_downloaders(self) -> list[dict]:
        return [
            {
                "name": d.info.name,
                "version": d.info.version,
                "platforms": list(d.info.platforms),
                "priority": d.info.priority,
                "available": d.is_available,
            }
            for d in self._downloaders
        ]


_router: DownloaderRouter | None = None


def get_router() -> DownloaderRouter:
    global _router
    if _router is None:
        _router = DownloaderRouter()
    return _router
