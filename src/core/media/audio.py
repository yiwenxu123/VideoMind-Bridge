"""共享音频转码（阶段 3）

DashScope 需要 mp3、SenseVoice 需要 16k 单声道 wav、TikHub 需要抽音轨——
这些 ffmpeg 细节原本散落在多个模块，现在集中在这里。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .types import MediaTranscodeError

_FFMPEG_KNOWN_PATHS = (
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/usr/bin/ffmpeg",
    "/usr/local/ffmpeg/bin/ffmpeg",
)


def find_ffmpeg() -> str | None:
    """PATH → 常见安装路径。"""
    found = shutil.which("ffmpeg")
    if found:
        return found
    for path in _FFMPEG_KNOWN_PATHS:
        if Path(path).exists():
            return path
    return None


def _run_ffmpeg(args: list[str], dest: Path, timeout: float) -> Path:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise MediaTranscodeError("未找到 ffmpeg，无法转码音频")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", *args, str(dest)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0 or not dest.exists() or dest.stat().st_size < 1000:
            raise MediaTranscodeError(f"ffmpeg 转码失败: {(proc.stderr or '')[-200:]}")
        return dest
    except MediaTranscodeError:
        dest.unlink(missing_ok=True)
        raise
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise MediaTranscodeError(f"ffmpeg 转码异常: {exc}") from exc


def transcode_to_mp3(src: Path, dest: Path, timeout: float = 180.0) -> Path:
    """任意容器 → mp3（DashScope / TikHub 使用）。"""
    return _run_ffmpeg(
        ["-i", str(src), "-vn", "-acodec", "libmp3lame", "-b:a", "128k"],
        dest,
        timeout,
    )


def to_16k_mono_wav(src: Path, dest: Path, timeout: float = 180.0) -> Path:
    """任意容器 → 16kHz 单声道 wav（SenseVoice 输入规格）。"""
    return _run_ffmpeg(
        ["-i", str(src), "-vn", "-ar", "16000", "-ac", "1"],
        dest,
        timeout,
    )
