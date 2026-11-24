"""视频任务数据模型定义"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID


class ExportTarget(Enum):
    """导出目标枚举"""
    OBSIDIAN = "obsidian"
    LOCAL = "local"
    NOTION = "notion"
    WEBHOOK = "webhook"


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
