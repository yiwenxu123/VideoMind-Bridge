"""yt-dlp 媒体下载器（阶段 3）

把原 ytdlp_asr 提取器里的“下载音频 / 转码兜底 / cookies 登录态 /
元信息 dump”整体搬到这里。提取器只保留：URL 支持判断 + ASR 链调用。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..platforms.ytdlp_options import ytdlp_cookie_args, ytdlp_network_args
from .audio import find_ffmpeg
from .types import FetchedMedia, MediaFetchFailed

logger = logging.getLogger(__name__)

_YTDLP_CMD = "yt-dlp"


def resolve_ytdlp() -> str | None:
    """解析 yt-dlp 可执行文件: PATH → 项目 venv → 常见路径。

    MCP 常以 `uv run` 启动, venv bin 在 PATH 中; 但独立进程/非登录 shell
    下 PATH 可能缺失, 此处显式兜底, 避免静默判为"未安装"。
    """
    found = shutil.which(_YTDLP_CMD)
    if found:
        return found
    # 项目 venv (跨平台: Unix bin / Windows Scripts)
    venv_root = Path(__file__).resolve().parents[3] / ".venv"
    for sub in ("Scripts", "bin"):
        for name in (_YTDLP_CMD, _YTDLP_CMD + ".exe"):
            candidate = venv_root / sub / name
            if candidate.exists():
                return str(candidate)
    candidate = Path.home() / ".local" / "bin" / _YTDLP_CMD
    if candidate.exists():
        return str(candidate)
    return None


class YtDlpMediaFetcher:
    """yt-dlp 下载器：原生 bestaudio 优先，失败时 --extract-audio 转码兜底。"""

    def __init__(self, ytdlp: str | None = None) -> None:
        self._ytdlp = ytdlp

    @property
    def binary(self) -> str | None:
        if self._ytdlp is None:
            self._ytdlp = resolve_ytdlp()
        return self._ytdlp

    def is_available(self) -> bool:
        return self.binary is not None

    def _cookies_args(self) -> list[str]:
        """下载所用登录态统一由 YtDlpSessionProvider 提供。"""
        return ytdlp_cookie_args()

    def _timeout(self, timeout: float | None) -> float:
        if timeout is not None:
            return timeout
        try:
            return float(os.getenv("VMB_DOWNLOAD_TIMEOUT", "300"))
        except ValueError:
            return 300.0

    def fetch(
        self,
        url: str,
        workdir: Path,
        timeout: float | None = None,
    ) -> FetchedMedia:
        """下载音频/视频；失败抛 MediaFetchFailed。"""
        if not self.is_available():
            raise MediaFetchFailed("yt-dlp 未安装 (pip install yt-dlp)")
        workdir.mkdir(parents=True, exist_ok=True)
        effective_timeout = self._timeout(timeout)

        audio = self._download_raw_audio(url, workdir, effective_timeout)
        if audio is not None:
            return FetchedMedia(
                path=audio, size=audio.stat().st_size, source="yt-dlp-raw"
            )

        ffmpeg = find_ffmpeg()
        if ffmpeg is not None:
            audio = self._download_with_transcode(url, workdir, ffmpeg, effective_timeout)
            if audio is not None:
                return FetchedMedia(
                    path=audio, size=audio.stat().st_size, source="yt-dlp-transcoded"
                )

        raise MediaFetchFailed(
            "yt-dlp 下载失败 (原生直下不可用"
            + ("" if ffmpeg else "; ffmpeg 未找到, 无法转码兜底")
            + ")"
        )

    def dump_metadata(self, url: str, timeout: float = 60.0) -> dict[str, Any]:
        """yt-dlp --dump-json --skip-download；失败返回空字典。"""
        if not self.is_available():
            return {}
        cmd = [
            self.binary or _YTDLP_CMD,
            "--dump-json",
            "--skip-download",
            *ytdlp_network_args(url),
            *self._cookies_args(),
            url,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0:
                line = result.stdout.strip().split("\n")[0]
                if line.startswith("{"):
                    return dict(json.loads(line))
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            pass
        return {}

    def _download_raw_audio(self, url: str, tmp_dir: Path, timeout: float) -> Path | None:
        """原生 bestaudio 直下 (无后处理, 不依赖 ffmpeg)。"""
        output_template = str(tmp_dir / "%(id)s.%(ext)s")
        cmd = [
            self.binary or _YTDLP_CMD,
            "-f", "bestaudio/best",
            "--no-playlist",
            "--output", output_template,
            *ytdlp_network_args(url),
            *self._cookies_args(),
            url,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                logger.warning(
                    f"yt-dlp 原生音频下载失败 rc={result.returncode}: "
                    f"{result.stderr.strip()[-200:]}"
                )
                return None
            return self._find_audio_file(result, tmp_dir)
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning(f"yt-dlp 原生音频下载异常: {exc}")
            return None

    def _download_with_transcode(
        self, url: str, tmp_dir: Path, ffmpeg: str, timeout: float
    ) -> Path | None:
        """--extract-audio + --ffmpeg-location 转码下载 (兜底)。"""
        output_template = str(tmp_dir / "%(id)s.%(ext)s")
        cmd = [
            self.binary or _YTDLP_CMD,
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--no-playlist",
            "--output", output_template,
            "--ffmpeg-location", ffmpeg,
            *ytdlp_network_args(url),
            *self._cookies_args(),
            url,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                logger.warning(
                    f"yt-dlp 转码下载失败 rc={result.returncode}: "
                    f"{result.stderr.strip()[-200:]}"
                )
                return None
            return self._find_audio_file(result, tmp_dir)
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning(f"yt-dlp 转码下载异常: {exc}")
            return None

    @staticmethod
    def _find_audio_file(result: subprocess.CompletedProcess, tmp_dir: Path) -> Path | None:
        """定位下载的音频/视频文件。

        以目录真实落盘为准 (--print filename 对抖音等格式打印的推断路径不可靠),
        后缀覆盖 faster-whisper/PyAV 可解码的常见容器。
        """
        suffixes = (
            ".mp3", ".m4a", ".wav", ".aac", ".opus", ".webm",
            ".mp4", ".m4s", ".flac", ".ogg",
        )

        # 1) stdout 辅助 (存在且后缀合法时才采信)
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line:
                candidate = Path(line)
                if candidate.exists() and candidate.suffix in suffixes:
                    return candidate

        # 2) 目录真实落盘: 取最新生成的可解码文件
        files = [
            f for f in tmp_dir.iterdir()
            if f.is_file() and f.suffix in suffixes
            and f.stat().st_size > 1000
        ]
        if files:
            return max(files, key=lambda p: p.stat().st_mtime)

        return None
