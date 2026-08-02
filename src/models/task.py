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

