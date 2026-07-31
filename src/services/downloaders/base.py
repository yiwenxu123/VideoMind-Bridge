"""下载器基类

定义所有下载器必须实现的接口。
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

from ...models.task import VideoMetadata
from ...utils.platform_detector import detect_platform


class DownloaderCapability(Enum):
    """下载器能力"""
    VIDEO = auto()          # 支持视频下载
    AUDIO_ONLY = auto()     # 支持仅音频下载
    METADATA = auto()       # 支持获取元数据
    PLAYLIST = auto()       # 支持播放列表
    SUBTITLE = auto()       # 支持字幕下载
    THUMBNAIL = auto()      # 支持缩略图下载
    LIVE_STREAM = auto()    # 支持直播流


@dataclass
class DownloaderInfo:
    """下载器信息"""
    name: str                           # 下载器名称
    version: str                        # 版本号
    platforms: set[str]                 # 支持的平台
    capabilities: set[DownloaderCapability]  # 支持的能力
    priority: int = 100                 # 优先级（数字越小优先级越高）
    description: str = ""               # 描述


@dataclass
class DownloadOptions:
    """下载选项"""
    output_dir: Path                                    # 输出目录
    keep_video: bool = False                            # 是否保留视频
    video_quality: str = "best"                         # 视频质量
    audio_quality: str = "best"                         # 音频质量
    audio_format: str = "m4a"                           # 音频格式
    video_format: str = "mp4"                           # 视频格式
    subtitle_languages: list[str] = field(default_factory=list)  # 字幕语言
    cookies: str | None = None                       # Cookies 字符串
    cookies_file: Path | None = None                 # Cookies 文件路径
    cookies_from_browser: str | None = None          # 浏览器名称（chrome/safari/firefox）
    proxy: str | None = None                         # 代理地址
    timeout: int = 300                                  # 超时时间（秒）
    retries: int = 3                                    # 重试次数


ProgressCallback = Callable[[str, float], None]


@dataclass
class DownloadResult:
    """下载结果"""
    success: bool                                       # 是否成功
    audio_path: Path | None = None                   # 音频文件路径
    video_path: Path | None = None                   # 视频文件路径
    metadata: VideoMetadata | None = None            # 视频元数据
    subtitle_paths: list[Path] = field(default_factory=list)  # 字幕文件路径
    thumbnail_path: Path | None = None               # 缩略图路径
    error_message: str | None = None                 # 错误信息
    error_code: str | None = None                    # 错误代码


class DownloaderBase(ABC):
    """下载器基类

    所有下载器必须继承此类并实现相应方法。
    """

    @property
    @abstractmethod
    def info(self) -> DownloaderInfo:
        """获取下载器信息"""
        ...

    @property
    def is_available(self) -> bool:
        """检查下载器是否可用"""
        return True

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """
        检查是否能处理该 URL

        Args:
            url: 视频 URL

        Returns:
            是否能处理
        """
        ...

    @abstractmethod
    def download(
        self,
        url: str,
        options: DownloadOptions,
        progress_callback: ProgressCallback | None = None
    ) -> DownloadResult:
        """
        下载视频

        Args:
            url: 视频 URL
            options: 下载选项
            progress_callback: 进度回调函数

        Returns:
            下载结果
        """
        ...

    def get_metadata(self, _url: str) -> VideoMetadata | None:
        """
        获取视频元数据（不下载）

        Args:
            url: 视频 URL

        Returns:
            视频元数据，如果不支持则返回 None
        """
        return None

    def get_supported_platforms(self) -> set[str]:
        """
        获取支持的平台列表

        Returns:
            平台名称集合
        """
        return self.info.platforms

    def has_capability(self, capability: DownloaderCapability) -> bool:
        """
        检查是否具有指定能力

        Args:
            capability: 能力类型

        Returns:
            是否具有该能力
        """
        return capability in self.info.capabilities

    def _detect_platform(self, url: str) -> str:
        """检测 URL 对应的平台"""
        return detect_platform(url)
