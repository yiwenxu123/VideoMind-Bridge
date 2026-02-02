"""时间工具模块"""

from typing import List


def format_time_for_srt(seconds: float) -> str:
    """
    格式化为 SRT 时间格式 HH:MM:SS,mmm

    Args:
        seconds: 秒数

    Returns:
        str: SRT 格式时间字符串
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_time_for_media_extended(seconds: int) -> str:
    """
    格式化为 Media Extended 插件支持的时间格式 HH:MM:SS

    Args:
        seconds: 秒数

    Returns:
        str: HH:MM:SS 格式时间字符串
    """
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def seconds_to_time_str(seconds: float) -> str:
    """
    将秒数转换为时间字符串 [HH:MM:SS]

    Args:
        seconds: 秒数

    Returns:
        str: [HH:MM:SS] 格式时间字符串
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"


def parse_time_str(time_str: str) -> float:
    """
    解析时间字符串为秒数

    Args:
        time_str: 时间字符串 (HH:MM:SS 或 MM:SS)

    Returns:
        float: 秒数
    """
    parts = time_str.strip("[]").split(":")
    if len(parts) == 3:
        hours, minutes, seconds = map(int, parts)
        return hours * 3600 + minutes * 60 + seconds
    elif len(parts) == 2:
        minutes, seconds = map(int, parts)
        return minutes * 60 + seconds
    else:
        raise ValueError(f"无法解析时间格式: {time_str}")
