"""服务层接口定义

定义核心服务的抽象接口，支持多种实现方式。
遵循依赖倒置原则：高层模块依赖抽象，不依赖具体实现。
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..models.task import Highlight, TranscriptSegment, VideoMetadata

# ============ 回调类型定义 ============

ProgressCallback = Callable[[float, str], None]
"""
进度回调函数类型

Args:
    progress: 进度百分比 (0.0 - 100.0)
    message: 当前步骤描述
"""


# ============ 下载服务接口 ============

@dataclass
class DownloadResult:
    """下载结果"""
    audio_path: Path
    video_path: Path | None = None
    metadata: VideoMetadata | None = None


class IDownloadService(Protocol):
    """
    视频下载服务接口 (Protocol 版本)

    支持静态类型检查，任何实现以下方法的类都被视为有效实现。
    """

    def download(
        self,
        url: str,
        progress_callback: ProgressCallback | None = None,
        keep_video: bool = False
    ) -> DownloadResult:
        """下载视频/音频"""
        ...

    def get_metadata(self, url: str) -> VideoMetadata | None:
        """获取视频元数据"""
        ...

    def supports(self, url: str) -> bool:
        """检查是否支持该 URL"""
        ...


class DownloadServiceInterface(ABC):
    """
    视频下载服务接口 (ABC 版本)

    负责从各种平台下载视频/音频
    """

    @abstractmethod
    def download(
        self,
        url: str,
        progress_callback: ProgressCallback | None = None,
        keep_video: bool = False
    ) -> DownloadResult:
        """
        下载视频/音频

        Args:
            url: 视频链接
            progress_callback: 进度回调函数
            keep_video: 是否保留原始视频文件

        Returns:
            DownloadResult: 下载结果，包含音频路径和元数据

        Raises:
            DownloadError: 下载失败
            UnsupportedPlatformError: 不支持的平台
        """
        raise NotImplementedError()

    @abstractmethod
    def get_metadata(self, url: str) -> VideoMetadata | None:
        """
        获取视频元数据（不下载）

        Args:
            url: 视频链接

        Returns:
            VideoMetadata: 视频元数据
        """
        raise NotImplementedError()

    @abstractmethod
    def supports(self, url: str) -> bool:
        """
        检查是否支持该URL

        Args:
            url: 视频链接

        Returns:
            bool: 是否支持
        """
        raise NotImplementedError()


# ============ 转录服务接口 ============

@dataclass
class TranscriptResult:
    """转录结果"""
    segments: list[TranscriptSegment]
    language: str
    language_probability: float
    full_text: str


class ITranscribeService(Protocol):
    """
    语音转录服务接口 (Protocol 版本)
    """

    def transcribe(
        self,
        audio_path: Path,
        model_size: str = "small",
        language: str | None = "zh",
        progress_callback: ProgressCallback | None = None
    ) -> TranscriptResult:
        """转录音频为文本"""
        ...


class TranscribeServiceInterface(ABC):
    """
    语音转录服务接口

    基于 faster-whisper 实现
    """

    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        model_size: str = "small",
        language: str | None = "zh",
        progress_callback: ProgressCallback | None = None
    ) -> TranscriptResult:
        """
        转录音频为文本

        Args:
            audio_path: 音频文件路径
            model_size: Whisper 模型大小 (tiny/base/small/medium/large)
            language: 语言代码 (zh/en/ja/...)，None 表示自动检测
            progress_callback: 进度回调

        Returns:
            TranscriptResult: 转录结果

        Raises:
            TranscribeError: 转录失败
        """
        raise NotImplementedError()

    @abstractmethod
    def get_available_models(self) -> list[str]:
        """
        获取可用的模型列表

        Returns:
            List[str]: 模型名称列表
        """
        raise NotImplementedError()


# ============ AI 服务接口 ============

@dataclass
class SummaryResult:
    """摘要结果"""
    title: str
    summary: str
    highlights: list[Highlight] = field(default_factory=list)
    model: str = ""
    tokens_used: int | None = None
    cost: float | None = None


@dataclass
class AISummaryInput:
    """AI 摘要输入"""
    transcript: str
    title: str | None = None
    author: str | None = None
    platform: str | None = None
    duration: int | None = None
    language: str = "zh"


class IAIProvider(Protocol):
    """
    AI 提供商接口 (Protocol 版本)

    支持多种 AI 模型实现，包括：
    - AIService (原有实现)
    - DeepSeekSkill (Skills 实现)
    - OpenAISkill (未来实现)
    - OllamaSkill (未来实现)
    """

    def generate_summary(
        self,
        input_data: AISummaryInput,
        progress_callback: ProgressCallback | None = None
    ) -> SummaryResult:
        """生成摘要"""
        ...

    def is_available(self) -> bool:
        """检查服务是否可用"""
        ...


class AIServiceInterface(ABC):
    """
    AI 服务接口 (ABC 版本)

    支持多厂商 LLM (OpenAI/DeepSeek/Anthropic/本地Ollama)
    """

    @abstractmethod
    def summarize(
        self,
        transcript: str,
        prompt_template: str,
        provider: str,
        model: str | None = None,
        progress_callback: ProgressCallback | None = None
    ) -> SummaryResult:
        """
        生成视频摘要

        Args:
            transcript: 转录文本
            prompt_template: Prompt 模板（支持变量注入）
            provider: AI 提供商名称
            model: 指定模型名称（可选，使用默认）
            progress_callback: 进度回调

        Returns:
            SummaryResult: 摘要结果

        Raises:
            AIError: AI 调用失败
            RateLimitError: API 限流
        """
        raise NotImplementedError()

    @abstractmethod
    def get_available_providers(self) -> list[str]:
        """
        获取可用的 AI 提供商列表

        Returns:
            List[str]: 提供商名称列表
        """
        raise NotImplementedError()

    @abstractmethod
    def validate_provider_config(self, provider: str) -> bool:
        """
        验证提供商配置是否有效

        Args:
            provider: 提供商名称

        Returns:
            bool: 配置是否有效
        """
        raise NotImplementedError()


# ============ 导出服务接口 ============

@dataclass
class ExportInput:
    """导出输入"""
    title: str
    author: str
    platform: str
    url: str
    transcript: str | None = None
    summary: str | None = None
    highlights: list[Highlight] = field(default_factory=list)
    audio_path: Path | None = None
    video_path: Path | None = None
    duration: int = 0
    created_at: str | None = None


@dataclass
class ExportOutput:
    """导出输出"""
    success: bool
    output_path: Path | None = None
    error_message: str | None = None
    format: str = ""


class IExporter(Protocol):
    """
    导出器接口 (Protocol 版本)

    支持多种导出目标，包括：
    - LocalExporter (原有实现)
    - ObsidianExporter (原有实现)
    - LocalExportSkill (Skills 实现)
    - ObsidianExportSkill (Skills 实现)
    - NotionExporter (未来实现)
    """

    @property
    def name(self) -> str:
        """导出器名称"""
        ...

    def export(
        self,
        input_data: ExportInput,
        progress_callback: ProgressCallback | None = None
    ) -> ExportOutput:
        """执行导出"""
        ...

    def is_available(self) -> bool:
        """检查导出器是否可用"""
        ...


class IExportOrchestrator(Protocol):
    """
    导出编排器接口 (Protocol 版本)

    管理多个导出目标，协调并发导出。
    """

    def export_all(
        self,
        input_data: ExportInput,
        progress_callback: ProgressCallback | None = None
    ) -> list[ExportOutput]:
        """执行所有导出"""
        ...

    def get_exporters(self) -> list[IExporter]:
        """获取所有导出器"""
        ...
