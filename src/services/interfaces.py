"""服务层接口定义"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Protocol

from ..models.task import TranscriptSegment, VideoMetadata


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
    video_path: Optional[Path]  # 如果用户选择保留视频
    metadata: VideoMetadata


class DownloadServiceInterface(ABC):
    """
    视频下载服务接口
    
    负责从各种平台下载视频/音频
    """
    
    @abstractmethod
    def download(
        self,
        url: str,
        progress_callback: Optional[ProgressCallback] = None,
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
            UnsupportedPlatformError: 不支持的平
        """
        raise NotImplementedError()
    
    @abstractmethod
    def get_metadata(self, url: str) -> VideoMetadata:
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
    segments: List[TranscriptSegment]
    language: str
    language_probability: float
    full_text: str  # 完整文本（去时间戳）


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
        language: Optional[str] = "zh",
        progress_callback: Optional[ProgressCallback] = None
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
    def get_available_models(self) -> List[str]:
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
    summary: str
    model: str
    tokens_used: Optional[int] = None
    cost: Optional[float] = None  # 估算成本


class AIServiceInterface(ABC):
    """
    AI 服务接口
    
    支持多厂商 LLM (OpenAI/DeepSeek/Anthropic/本地Ollama)
    """
    
    @abstractmethod
    def summarize(
        self,
        transcript: str,
        prompt_template: str,
        provider: str,
        model: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None
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
    def get_available_providers(self) -> List[str]:
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
