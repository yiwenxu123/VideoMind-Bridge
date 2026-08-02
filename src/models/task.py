"""视频任务数据模型定义"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
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
    thumbnail_url: str | None = None
    description: str | None = None
    published_at: datetime | None = None
    raw_info: dict[str, Any] = field(default_factory=dict)  # 原始平台数据


@dataclass
class TranscriptSegment:
    """转录文本片段"""
    start: float  # 开始时间（秒）
    end: float  # 结束时间（秒）
    text: str
    confidence: float | None = None  # 置信度


@dataclass
class Highlight:
    """时间轴要点"""
    time: str  # 格式化时间 (MM:SS)
    seconds: int  # 绝对秒数
    content: str  # 要点内容


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
    video_path: Path | None = None
    audio_path: Path | None = None
    transcript_path: Path | None = None

    # 内容数据
    transcript_segments: list[TranscriptSegment] = field(default_factory=list)
    transcript_text: str | None = None  # 完整转录文本
    ai_summary: str | None = None  # AI生成的摘要

    # 配置信息
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExportResult:
    """导出结果"""
    success: bool
    target: ExportTarget
    timestamp: datetime = field(default_factory=datetime.now)
    error_msg: str | None = None
    output_path: Path | None = None  # 本地输出路径
    remote_url: str | None = None  # 远程链接（如Notion页面）
    metadata: dict[str, Any] = field(default_factory=dict)


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
    targets: set[ExportTarget] = field(default_factory=lambda: {ExportTarget.LOCAL})
    ai_provider: str | None = None  # AI提供商名称
    ai_prompt: str | None = None  # 使用的Prompt模板
    cookies_from_browser: str | None = None  # 浏览器Cookie来源
    allow_downgrade: bool = False  # AI不可用时是否降级为转录存档

    # 状态追踪
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0  # 0.0 - 100.0
    current_step: str = ""  # 当前步骤描述

    # 元数据（解析URL后填充）
    metadata: VideoMetadata | None = None

    # 结果数据
    audio_path: Path | None = None
    transcript_segments: list[TranscriptSegment] = field(default_factory=list)
    ai_summary: str | None = None
    export_results: list[ExportResult] = field(default_factory=list)

    # 错误信息
    error_msg: str | None = None
    retry_count: int = 0
    completed_at: datetime | None = None

    # 输出文件
    output_files: list[Path] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "id": str(self.id),
            "url": self.url,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "mode": self.mode.value,
            "targets": [t.value for t in self.targets],
            "ai_provider": self.ai_provider,
            "ai_prompt": self.ai_prompt,
            "status": self.status.value,
            "progress": self.progress,
            "current_step": self.current_step,
            "metadata": self._metadata_to_dict(self.metadata),
            "audio_path": str(self.audio_path) if self.audio_path else None,
            "transcript_segments": [
                {"start": s.start, "end": s.end, "text": s.text, "confidence": s.confidence}
                for s in self.transcript_segments
            ],
            "ai_summary": self.ai_summary,
            "export_results": [self._export_result_to_dict(r) for r in self.export_results],
            "error_msg": self.error_msg,
            "retry_count": self.retry_count,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "output_files": [str(p) for p in self.output_files],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VideoTask":
        """从字典反序列化"""
        return cls(
            id=UUID(data["id"]) if isinstance(data.get("id"), str) else data.get("id", uuid4()),
            url=data.get("url", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at", datetime.now()),
            updated_at=datetime.fromisoformat(data["updated_at"]) if isinstance(data.get("updated_at"), str) else data.get("updated_at", datetime.now()),
            mode=ProcessingMode(data["mode"]) if isinstance(data.get("mode"), str) else data.get("mode", ProcessingMode.FULL),
            targets={ExportTarget(t) for t in data.get("targets", ["local"])},
            ai_provider=data.get("ai_provider"),
            ai_prompt=data.get("ai_prompt"),
            status=TaskStatus(data["status"]) if isinstance(data.get("status"), str) else data.get("status", TaskStatus.PENDING),
            progress=data.get("progress", 0.0),
            current_step=data.get("current_step", ""),
            metadata=cls._metadata_from_dict(data.get("metadata")),
            audio_path=Path(data["audio_path"]) if data.get("audio_path") else None,
            transcript_segments=[
                TranscriptSegment(**s) for s in data.get("transcript_segments", [])
            ],
            ai_summary=data.get("ai_summary"),
            export_results=[cls._export_result_from_dict(r) for r in data.get("export_results", [])],
            error_msg=data.get("error_msg"),
            retry_count=data.get("retry_count", 0),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            output_files=[Path(p) for p in data.get("output_files", [])],
        )

    @staticmethod
    def _metadata_to_dict(metadata: VideoMetadata | None) -> dict[str, Any] | None:
        """将 VideoMetadata 转换为字典"""
        if metadata is None:
            return None
        return {
            "title": metadata.title,
            "author": metadata.author,
            "duration": metadata.duration,
            "platform": metadata.platform,
            "url": metadata.url,
            "thumbnail_url": metadata.thumbnail_url,
            "description": metadata.description,
            "published_at": metadata.published_at.isoformat() if metadata.published_at else None,
            "raw_info": metadata.raw_info,
        }

    @staticmethod
    def _metadata_from_dict(data: dict[str, Any] | None) -> VideoMetadata | None:
        """从字典创建 VideoMetadata"""
        if data is None:
            return None
        return VideoMetadata(
            title=data.get("title", ""),
            author=data.get("author", ""),
            duration=data.get("duration", 0),
            platform=data.get("platform", ""),
            url=data.get("url", ""),
            thumbnail_url=data.get("thumbnail_url"),
            description=data.get("description"),
            published_at=datetime.fromisoformat(data["published_at"]) if data.get("published_at") else None,
            raw_info=data.get("raw_info", {}),
        )

    @staticmethod
    def _export_result_to_dict(result: ExportResult) -> dict[str, Any]:
        """将 ExportResult 转换为字典"""
        return {
            "success": result.success,
            "target": result.target.value,
            "timestamp": result.timestamp.isoformat(),
            "error_msg": result.error_msg,
            "output_path": str(result.output_path) if result.output_path else None,
            "remote_url": result.remote_url,
            "metadata": result.metadata,
        }

    @staticmethod
    def _export_result_from_dict(data: dict[str, Any]) -> ExportResult:
        """从字典创建 ExportResult"""
        target_value = data.get("target")
        if isinstance(target_value, str):
            target = ExportTarget(target_value)
        elif isinstance(target_value, ExportTarget):
            target = target_value
        else:
            target = ExportTarget.LOCAL
        return ExportResult(
            success=data.get("success", False),
            target=target,
            timestamp=datetime.fromisoformat(data["timestamp"]) if isinstance(data.get("timestamp"), str) else data.get("timestamp", datetime.now()),
            error_msg=data.get("error_msg"),
            output_path=Path(data["output_path"]) if data.get("output_path") else None,
            remote_url=data.get("remote_url"),
            metadata=data.get("metadata", {}),
        )


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
    targets: list[ExportTarget]  # 导出目标

    # 状态信息
    status: TaskStatus  # 最终状态
    error_msg: str | None = None  # 错误信息（如果失败）

    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    # 结果数据
    summary: str | None = None  # AI摘要内容
    highlights_count: int = 0  # 要点数量
    transcript_path: Path | None = None  # 转录文件路径

    # 导出结果
    output_files: list[Path] = field(default_factory=list)  # 输出文件列表
    export_success_count: int = 0  # 成功导出数
    export_total_count: int = 0  # 总导出数

    def to_dict(self) -> dict[str, Any]:
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
    def from_dict(cls, data: dict[str, Any]) -> "TaskHistory":
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
