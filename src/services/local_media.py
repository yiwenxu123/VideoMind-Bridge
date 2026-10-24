"""本地媒体文件识别与校验。

用于把人工下载的视频/音频接入 v1 处理链，跳过平台下载。
"""

from __future__ import annotations

import os
from pathlib import Path

from ..utils.exceptions import ValidationError

VIDEO_EXTENSIONS = frozenset({".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"})
AUDIO_EXTENSIONS = frozenset({".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".opus", ".amr"})
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


def is_remote_url(value: str) -> bool:
    return value.strip().lower().startswith(("http://", "https://"))


def is_local_media_path(value: str) -> bool:
    """判断输入是否是已存在且格式受支持的本地媒体文件。"""
    if not value or is_remote_url(value):
        return False
    path = Path(value).expanduser()
    return path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS


def resolve_local_media_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.exists() or not path.is_file():
        raise ValidationError(
            f"本地文件不存在: {path}",
            error_code="INVALID_PATH",
            details={"path": str(path)},
        )
    if path.suffix.lower() not in MEDIA_EXTENSIONS:
        raise ValidationError(
            f"不支持的本地文件格式: {path.suffix}",
            error_code="INVALID_PATH",
            details={"path": str(path), "suffix": path.suffix},
        )
    return path.resolve()


def get_allowed_local_roots() -> list[Path]:
    """API 本地文件入口的允许目录，来自 VMB_LOCAL_MEDIA_DIRS。"""
    raw = os.environ.get("VMB_LOCAL_MEDIA_DIRS", "")
    return [
        Path(item.strip()).expanduser().resolve()
        for item in raw.split(os.pathsep)
        if item.strip()
    ]


def resolve_allowed_local_media_path(value: str) -> Path:
    """API 专用：本地文件必须位于显式配置的允许目录内。"""
    path = resolve_local_media_path(value)
    roots = get_allowed_local_roots()
    if not roots:
        raise ValidationError(
            "API 本地文件入口未启用，请设置 VMB_LOCAL_MEDIA_DIRS",
            error_code="LOCAL_PATH_NOT_ALLOWED",
        )
    if not any(path.is_relative_to(root) for root in roots):
        raise ValidationError(
            "本地文件不在允许目录内",
            error_code="LOCAL_PATH_NOT_ALLOWED",
            details={"path": str(path), "allowed_dirs": [str(r) for r in roots]},
        )
    return path
