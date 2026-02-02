"""主应用类"""

from pathlib import Path
from typing import Optional

from .models.task import VideoTask, ProcessingMode, ExportTarget
from .services.interfaces import (
    DownloadServiceInterface,
    TranscribeServiceInterface,
    AIServiceInterface,
)
from .utils.config import AppConfig, ConfigManager


class VideoMindApp:
    """
    VideoMind Bridge 主应用类
    
    负责协调各个服务组件，管理任务队列
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        初始化应用
        
        Args:
            config_path: 配置文件路径，None 使用默认路径
        """
        self.config_manager = ConfigManager(config_path)
        self.config: Optional[AppConfig] = None
        
        # 服务组件（延迟初始化）
        self._download_service: Optional[DownloadServiceInterface] = None
        self._transcribe_service: Optional[TranscribeServiceInterface] = None
        self._ai_service: Optional[AIServiceInterface] = None
        
        # 任务队列
        self._tasks: dict = {}
    
    def initialize(self) -> None:
        """初始化应用（加载配置、初始化服务）"""
        raise NotImplementedError()
    
    def create_task(
        self,
        url: str,
        mode: ProcessingMode = ProcessingMode.FULL,
        targets: Optional[set[ExportTarget]] = None
    ) -> VideoTask:
        """
        创建新任务
        
        Args:
            url: 视频链接
            mode: 处理模式
            targets: 导出目标集合
            
        Returns:
            VideoTask: 创建的任务对象
        """
        raise NotImplementedError()
    
    def start_task(self, task_id: str) -> None:
        """启动任务"""
        raise NotImplementedError()
    
    def cancel_task(self, task_id: str) -> None:
        """取消任务"""
        raise NotImplementedError()
    
    def get_task_status(self, task_id: str) -> dict:
        """获取任务状态"""
        raise NotImplementedError()
    
    def shutdown(self) -> None:
        """关闭应用，清理资源"""
        raise NotImplementedError()
