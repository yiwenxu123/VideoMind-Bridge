"""数据模型模块

（2026-11-25 A2：v1 任务模型 VideoTask/TaskStatus/ProcessingMode/TaskHistory 已删除）
"""

from .task import (
    ExportContext,
    ExportResult,
    ExportTarget,
    Highlight,
    TranscriptSegment,
    VideoMetadata,
)

__all__ = [
    "VideoMetadata",
    "ExportTarget",
    "ExportContext",
    "ExportResult",
    "Highlight",
    "TranscriptSegment",
]
