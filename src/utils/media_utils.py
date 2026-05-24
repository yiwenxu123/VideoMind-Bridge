"""媒体工具模块"""

from typing import Any

from ..models.task import Highlight, TranscriptSegment
from .time_utils import format_time_for_srt


def generate_srt(segments: list[TranscriptSegment]) -> str:
    """
    生成 SRT 字幕格式

    Args:
        segments: 转录段落列表

    Returns:
        str: SRT 格式字幕内容
    """
    lines = []
    for i, seg in enumerate(segments, 1):
        start = format_time_for_srt(seg.start)
        end = format_time_for_srt(seg.end)
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(seg.text)
        lines.append("")
    return "\n".join(lines)


def extract_highlights_from_context(context: dict[str, Any]) -> list[Highlight]:
    """
    从上下文提取时间轴数据

    Args:
        context: 包含 highlights 的配置字典

    Returns:
        List[Highlight]: 时间轴列表
    """
    highlights_data = context.get("highlights", [])

    highlights = []
    for h in highlights_data:
        if isinstance(h, dict):
            highlights.append(Highlight(
                time=h.get("time", "00:00:00"),
                seconds=h.get("seconds", 0),
                content=h.get("content", "")
            ))

    return highlights
