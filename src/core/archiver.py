"""提取即归档: 把 v2 ExtractResult 直接归档, 无需经过 v1 下载/转录

职责边界:
- 输入: v2 提取结果 (ExtractResult, 含全文/时间轴/元信息)
- 输出: 各归档目标 (Obsidian / 本地 / HTML 播放器) 的导出结果
- 不依赖 video_path/audio_path — 导出器在无媒体时降级为纯文本笔记
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..exporters.html_player_exporter import HTMLPlayerExporter
from ..models.task import (
    ExportContext,
    ExportResult,
    ExportTarget,
    TranscriptSegment,
    VideoMetadata,
)
from ..services.export_orchestrator import ExportOrchestrator
from ..utils import get_logger
from .models import ExtractResult

logger = get_logger(__name__)

# 支持的归档目标
SUPPORTED_ARCHIVE_TARGETS = ("obsidian", "local", "html_player")


@dataclass
class ArchiverConfig:
    """归档配置"""

    # Obsidian
    obsidian_vault_path: Path | None = None
    obsidian_subfolder: str = "Inbox/Videos"
    # 本地
    local_output_path: Path | None = None
    local_organize_by: str = "date"
    # HTML 播放器
    html_enabled: bool = False


def build_export_context(
    result: ExtractResult,
    ai_summary: str | None = None,
) -> ExportContext:
    """把 v2 ExtractResult 转为 ExportContext (纯文本归档模式)

    Args:
        result: v2 提取结果
        ai_summary: 可选 AI 摘要 (写入笔记的"一句话总结")

    Returns:
        ExportContext: 无 video_path/audio_path 的纯文本归档上下文
    """
    metadata = VideoMetadata(
        title=result.title or "未命名视频",
        author="",
        duration=int(result.duration_seconds),
        platform=result.platform,
        url=result.url,
        raw_info={
            "source": result.source,
            "cost_tier": result.cost_tier.value,
        },
    )

    segments = [
        TranscriptSegment(
            start=float(s.get("start", 0) or 0),
            end=float(s.get("end", 0) or 0),
            text=str(s.get("text", "")),
        )
        for s in (result.segments or [])
    ]

    return ExportContext(
        task_id=uuid4(),
        video_metadata=metadata,
        transcript_segments=segments,
        transcript_text=result.content,
        ai_summary=ai_summary,
        config={
            "highlights": (result.metadata or {}).get("highlights", []),
        },
    )


def archive_extract_result(
    result: ExtractResult,
    targets: list[str] | None = None,
    config: ArchiverConfig | None = None,
    ai_summary: str | None = None,
) -> list[ExportResult]:
    """把提取结果直接归档到目标

    Args:
        result: v2 提取结果 (须有真实内容)
        targets: 归档目标 (obsidian / local / html_player)
        config: 归档配置
        ai_summary: 可选 AI 摘要

    Returns:
        list[ExportResult]: 各目标导出结果 (任一失败不影响其他)
    """
    if not result.success or not result.content.strip():
        return [
            ExportResult(
                success=False,
                target=ExportTarget.LOCAL,
                error_msg="提取结果无真实内容, 无法归档",
            )
        ]

    config = config or ArchiverConfig()
    targets = targets or ["obsidian", "local"]

    # 校验目标合法性
    invalid = [t for t in targets if t not in SUPPORTED_ARCHIVE_TARGETS]
    if invalid:
        logger.warning(f"未知归档目标被忽略: {invalid}")

    context = build_export_context(result, ai_summary)

    orchestrator_config: dict[str, Any] = {
        "local_output_path": config.local_output_path or Path.home() / "Downloads" / "VideoMind",
        "organize_by": config.local_organize_by,
        "obsidian_vault_path": config.obsidian_vault_path,
        "obsidian_subfolder": config.obsidian_subfolder,
    }

    target_enums: list[ExportTarget] = []
    if "obsidian" in targets:
        target_enums.append(ExportTarget.OBSIDIAN)
    if "local" in targets:
        target_enums.append(ExportTarget.LOCAL)

    results: list[ExportResult] = []
    if target_enums:
        orchestrator = ExportOrchestrator(targets=target_enums, config=orchestrator_config)
        results = orchestrator.export_all(context)

    if "html_player" in targets:
        results.append(_archive_html_player(context, config))

    return results


def _archive_html_player(context: ExportContext, config: ArchiverConfig) -> ExportResult:
    """HTML 播放器归档 (无本地视频时降级失败, 不阻塞其他目标)"""
    exporter = HTMLPlayerExporter()
    try:
        return exporter.export(context)
    except Exception as e:
        logger.error(f"HTML 播放器导出失败: {e}")
        return ExportResult(
            success=False,
            target=ExportTarget.LOCAL,
            error_msg=f"HTML 播放器导出失败: {e}",
        )


__all__ = [
    "ArchiverConfig",
    "SUPPORTED_ARCHIVE_TARGETS",
    "archive_extract_result",
    "build_export_context",
]
