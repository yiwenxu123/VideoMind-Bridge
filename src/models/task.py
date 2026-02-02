"""视频任务数据模型定义"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4


class ProcessingMode(Enum):
    """处理模式枚举"""
    FULL = "full"  # 完整处理: 下载 → 转录 → AI摘要 → 导出
    DOWNLOAD_ONLY = "download_only"  # 仅下载原始视频/音频
    TRANSCRIBE_ONLY = "transcribe_only"  # 下载 → 转录生成SRT，不调用AI


class ExportTarget(Enum):
    """导出目标枚举"""
    OBSIDIAN = "obsidian"
    LOCAL = "local"
    NOTION = "notion"
    WEBHOOK = "webhook"


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"  # 等待中
    DOWNLOADING = "downloading"  # 下载中
    TRANSCRIBING = "transcribing"  # 转录中
    AI_PROCESSING = "ai_processing"  # AI处理中
    EXPORTING = "exporting"  # 导出中
    PAUSED = "paused"  # 已暂停
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


@dataclass
class VideoMetadata:
    """视频元数据"""
    title: str
    author: str
    duration: int  # 秒
    platform: str  # bilibili, youtube, etc.
    url: str
    thumbnail_url: Optional[str] = None
    description: Optional[str] = None
    published_at: Optional[datetime] = None
    raw_info: Dict[str, Any] = field(default_factory=dict)  # 原始平台数据


@dataclass
class TranscriptSegment:
    """转录文本片段"""
    start: float  # 开始时间（秒）
    end: float  # 结束时间（秒）
    text: str
    confidence: Optional[float] = None  # 置信度


@dataclass
class ExportContext:
    """
    导出上下文
    包含导出操作所需的所有数据和文件路径
    """
    # 任务信息
    task_id: UUID
    video_metadata: VideoMetadata
    
    # 文件路径（可能为None，取决于处理模式）
    video_path: Optional[Path] = None
    audio_path: Optional[Path] = None
    transcript_path: Optional[Path] = None
    
    # 内容数据
    transcript_segments: List[TranscriptSegment] = field(default_factory=list)
    transcript_text: Optional[str] = None  # 完整转录文本
    ai_summary: Optional[str] = None  # AI生成的摘要
    
    # 配置信息
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExportResult:
    """导出结果"""
    success: bool
    target: ExportTarget
    timestamp: datetime = field(default_factory=datetime.now)
    error_msg: Optional[str] = None
    output_path: Optional[Path] = None  # 本地输出路径
    remote_url: Optional[str] = None  # 远程链接（如Notion页面）
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoTask:
    """
    视频任务实体
    
    这是一个聚合根，包含任务的所有信息和状态
    """
    # 基础标识
    id: UUID = field(default_factory=uuid4)
    url: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # 处理配置
    mode: ProcessingMode = ProcessingMode.FULL
    targets: Set[ExportTarget] = field(default_factory=lambda: {ExportTarget.LOCAL})
    ai_provider: Optional[str] = None  # AI提供商名称
    ai_prompt: Optional[str] = None  # 使用的Prompt模板
    
    # 状态追踪
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0  # 0.0 - 100.0
    current_step: str = ""  # 当前步骤描述
    
    # 元数据（解析URL后填充）
    metadata: Optional[VideoMetadata] = None
    
    # 结果数据
    audio_path: Optional[Path] = None
    transcript_segments: List[TranscriptSegment] = field(default_factory=list)
    ai_summary: Optional[str] = None
    export_results: List[ExportResult] = field(default_factory=list)
    
    # 错误信息
    error_msg: Optional[str] = None
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        raise NotImplementedError()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoTask":
        """从字典反序列化"""
        raise NotImplementedError()


@dataclass
class TaskHistory:
    """
    任务历史记录

    用于持久化存储已完成的任务信息
    """
    # 基础标识
    id: str  # 任务ID
    url: str  # 视频URL
    title: str  # 视频标题
    author: str  # 视频作者
    platform: str  # 视频平台

    # 处理配置
    mode: ProcessingMode  # 处理模式
    targets: List[ExportTarget]  # 导出目标

    # 状态信息
    status: TaskStatus  # 最终状态
    error_msg: Optional[str] = None  # 错误信息（如果失败）

    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    # 结果数据
    summary: Optional[str] = None  # AI摘要内容
    highlights_count: int = 0  # 要点数量
    transcript_path: Optional[Path] = None  # 转录文件路径

    # 导出结果
    output_files: List[Path] = field(default_factory=list)  # 输出文件列表
    export_success_count: int = 0  # 成功导出数
    export_total_count: int = 0  # 总导出数

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "author": self.author,
            "platform": self.platform,
            "mode": self.mode.value,
            "targets": [t.value for t in self.targets],
            "status": self.status.value,
            "error_msg": self.error_msg,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "summary": self.summary,
            "highlights_count": self.highlights_count,
            "transcript_path": str(self.transcript_path) if self.transcript_path else None,
            "output_files": [str(p) for p in self.output_files],
            "export_success_count": self.export_success_count,
            "export_total_count": self.export_total_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskHistory":
        """从字典反序列化"""
        return cls(
            id=data["id"],
            url=data["url"],
            title=data["title"],
            author=data.get("author", ""),
            platform=data.get("platform", ""),
            mode=ProcessingMode(data["mode"]),
            targets=[ExportTarget(t) for t in data.get("targets", [])],
            status=TaskStatus(data["status"]),
            error_msg=data.get("error_msg"),
            created_at=datetime.fromisoformat(data["created_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            summary=data.get("summary"),
            highlights_count=data.get("highlights_count", 0),
            transcript_path=Path(data["transcript_path"]) if data.get("transcript_path") else None,
            output_files=[Path(p) for p in data.get("output_files", [])],
            export_success_count=data.get("export_success_count", 0),
            export_total_count=data.get("export_total_count", 0),
        )
