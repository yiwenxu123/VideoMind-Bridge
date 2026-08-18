"""yt-dlp + ASR 组合提取器

下载视频音频后通过语音识别转写文字，作为无字幕视频的通用兜底。
优先级在平台原生提取器之后，TikHub 付费 API 之前。

工作流程:
  1. yt-dlp 下载音频 (显式解析 yt-dlp/ffmpeg 路径, 不依赖 shell PATH)
  2. ASR 链路 (按顺序降级):
     a. 本地 faster-whisper (默认, 零 key 免费, 最可靠)  ← 主链路
     b. 阿里云 NLS paraformer-v2 (已配置时)
     c. DashScope paraformer-v2 (已配置时, 复用 dashscope_key)
  3. 全部 ASR 不可用时返回占位结果 (音频路径+配置指引)

成本: CHEAP (本地 whisper 免费; 云 ASR ~0.00008元/秒, 10分钟视频约0.048元)
环境变量:
  VMB_WHISPER_MODEL   本地 whisper 模型大小 (默认 base: tiny/base/small/medium)
  VMB_ASR_LANGUAGE    转写语言 (默认 None=自动检测, 如 zh/en)
  VMB_DOWNLOAD_TIMEOUT yt-dlp 下载超时秒数 (默认 300)
  VMB_COOKIES_BROWSER  借本机浏览器真实登录态下载 (值: chrome/edge/firefox/browser);
  VMB_COOKIES_FILE     使用 cookies.txt 文件登录态下载 (服务器/Windows 无浏览器场景权威)
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from ..models import CostTier, ExtractResult
from . import register_extractor
from ._dashscope_asr import transcribe_audio_data
from ._whisper_asr import transcribe_local
from .aliyun_asr_extractor import AliyunASRExtractor
from .base import ContentExtractor

logger = logging.getLogger(__name__)

_YTDLP_CMD = "yt-dlp"
_FFMPEG_KNOWN_PATHS = [
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/usr/bin/ffmpeg",
    "/usr/local/ffmpeg/bin/ffmpeg",
]

_SUPPORTED_PLATFORMS = [
    "bilibili", "douyin", "xiaohongshu", "youtube",
    "tiktok", "twitter", "x.com", "instagram", "ted",
]


def _resolve_ytdlp() -> str | None:
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


def _resolve_ffmpeg() -> str | None:
    """解析 ffmpeg 路径 (--extract-audio 依赖, 不在 PATH 时显式传入)。"""
    found = shutil.which("ffmpeg")
    if found:
        return found
    for p in _FFMPEG_KNOWN_PATHS:
        if Path(p).exists():
            return p
    return None


class YtDlpASRExtractor(ContentExtractor):
    """yt-dlp + ASR 组合提取器 (无字幕视频通用兜底, 本地 whisper 优先)"""

    platform_name = "ytdlp_asr"
    _cost_tier = CostTier.CHEAP
    url_pattern = re.compile(
        r"(youtube\.com|youtu\.be|bilibili\.com|b23\.tv|"
        r"douyin\.com|iesdouyin\.com|xiaohongshu\.com|xhslink\.(?:com|cn)|"
        r"twitter\.com|x\.com|tiktok\.com|instagram\.com|ted\.com)"
    )

    def __init__(self) -> None:
        self._asr = AliyunASRExtractor()
        self._ytdlp: str | None = None
        self._ffmpeg: str | None = None
        self._available: bool | None = None
        self._cookies_browser = os.getenv("VMB_COOKIES_BROWSER", "").strip()

    def is_available(self) -> bool:
        """yt-dlp 可执行即可用 (本地 whisper 免费零 key, 不依赖云凭证)"""
        if self._available is not None:
            return self._available
        ytdlp = _resolve_ytdlp()
        self._available = ytdlp is not None
        if self._available:
            self._ytdlp = ytdlp
        return self._available

    def extract(self, url: str) -> ExtractResult:
        if not self.is_available():
            return ExtractResult(
                success=False, platform="ytdlp_asr", title="", content="",
                source="ytdlp_asr", url=url, cost_tier=CostTier.CHEAP,
                error="yt-dlp 未安装 (pip install yt-dlp)",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = self._download_audio(url, Path(tmp_dir))
            if not audio_path:
                return ExtractResult(
                    success=False, platform="ytdlp_asr", title="", content="",
                    source="ytdlp_asr", url=url, cost_tier=CostTier.CHEAP,
                    error="yt-dlp 下载音频失败 (网络/风控/ffmpeg 缺失)",
                )

            metadata = self._get_metadata(url)
            platform = metadata.get("platform", "video")
            title = metadata.get("title", audio_path.stem)
            duration = float(metadata.get("duration", 0))

            result: ExtractResult | None = None

            # ── ASR 链路 A: 本地 faster-whisper (默认, 零 key) ──────────────
            result = self._transcribe_local(audio_path, url, platform, title, duration)
            if result and result.success:
                return result

            # ── ASR 链路 B/C: 云 ASR 仅作可选增强 (已配置时) ───────────────
            if self._asr.is_available():
                result = self._asr.transcribe_audio(audio_path)
            else:
                dashscope_key = self._resolve_api_key("dashscope_key")
                if dashscope_key:
                    result = self._transcribe_dashscope(
                        audio_path, dashscope_key, url,
                        platform, title, duration,
                    )
                else:
                    result = None

            if result and result.success:
                result.url = url
                if not result.title or result.title == audio_path.stem:
                    result.title = title
                return result

            if result and result.error:
                logger.warning(f"ytdlp_asr 云转写失败: {result.error}")

            # ── 全部 ASR 不可用: 占位结果 ─────────────────────────────────
            whisper_hint = "本地 faster-whisper 未安装" if not self._whisper_importable() else "本地转写返回空"
            return ExtractResult(
                success=True,
                platform=platform,
                title=title,
                content=(
                    "[yt-dlp+ASR] 已下载音频但 ASR 全链路不可用\n"
                    f"原因: {whisper_hint}; 可选: 安装 faster-whisper (pip install faster-whisper), "
                    "或配置 ALIYUN_ACCESS_KEY_ID/SECRET/APPKEY 或 dashscope_key\n"
                ),
                source="ytdlp_asr",
                url=url,
                cost_tier=CostTier.CHEAP,
                duration_seconds=duration,
                is_placeholder=True,
                metadata={
                    "audio_path": str(audio_path),
                    "asr_available": False,
                    "platform_meta": metadata,
                },
            )

    # ─────────────────────────── ASR 实现 ───────────────────────────

    def _transcribe_local(
        self, audio_path: Path, url: str, platform: str, title: str, duration: float,
    ) -> ExtractResult | None:
        """本地 faster-whisper 转写 (零成本, 主链路)。

        失败/未安装时返回 None (不抛异常), 由调用方继续降级。
        """
        try:
            model_size = os.getenv("VMB_WHISPER_MODEL", "base")
            language = os.getenv("VMB_ASR_LANGUAGE", "") or None
            started = time.time()
            text, segments = transcribe_local(audio_path, language=language, model_size=model_size)
            elapsed = round(time.time() - started, 1)
            if not text:
                logger.warning(f"本地 whisper 返回空转录: {audio_path.name}")
                return None
            logger.info(f"✓ 本地 faster-whisper 转写完成 ({elapsed}s, model={model_size})")
            return ExtractResult(
                success=True,
                platform=platform,
                title=title or audio_path.stem,
                content=text,
                source="ytdlp_asr_local",
                url=url,
                cost_tier=CostTier.CHEAP,
                duration_seconds=duration,
                language=language or "auto",
                segments=segments,
                metadata={"asr_provider": "faster-whisper", "model": model_size},
            )
        except ImportError:
            logger.warning("faster-whisper 未安装, 跳过本地 ASR")
            return None
        except Exception as e:
            logger.warning(f"本地 faster-whisper 转写失败: {e}")
            return None

    @staticmethod
    def _whisper_importable() -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def _transcribe_dashscope(
        self, audio_path: Path, api_key: str, url: str,
        platform: str, title: str, duration: float,
    ) -> ExtractResult:
        """DashScope paraformer-v2 转写 (复用 dashscope_key, 免额外配置)"""
        try:
            text, segments = transcribe_audio_data(audio_path, api_key)

            return ExtractResult(
                success=bool(text),
                platform=platform,
                title=title or audio_path.stem,
                content=text or "DashScope ASR 返回了空转录",
                source="ytdlp_asr",
                url=url,
                cost_tier=self._cost_tier,
                duration_seconds=duration,
                language="zh",
                segments=segments,
                metadata={"api_provider": "dashscope_asr", "model": "paraformer-v2"},
            )
        except Exception as e:
            return ExtractResult(
                success=False,
                platform=platform,
                title=title or audio_path.stem,
                content="",
                source="ytdlp_asr",
                url=url,
                cost_tier=self._cost_tier,
                duration_seconds=duration,
                error=f"DashScope ASR 调用失败: {e}",
            )

    # ─────────────────────────── 下载/元信息 ───────────────────────────

    def _download_audio(self, url: str, tmp_dir: Path) -> Path | None:
        """下载音频。

        优先原生音频直下 (-f bestaudio, 无需 ffmpeg, faster-whisper 可直接解码);
        失败时兜底 --extract-audio 转码 (显式指定 ffmpeg 路径, 不依赖 PATH)。
        """
        ffmpeg = _resolve_ffmpeg()

        # 尝试 1: 原生音频, 免 ffmpeg
        audio = self._download_raw_audio(url, tmp_dir)
        if audio:
            return audio

        # 尝试 2: --extract-audio 转码兜底
        if ffmpeg:
            audio = self._download_with_transcode(url, tmp_dir, ffmpeg)
            if audio:
                return audio

        logger.warning(
            "yt-dlp 下载失败 (原生直下不可用"
            + ("" if ffmpeg else "; ffmpeg 未找到, 无法转码兜底")
            + ")"
        )
        return None

    def _cookies_args(self) -> list[str]:
        """下载所用登录态: 优先 cookies 文件 (VMB_COOKIES_FILE, 服务器场景),
        其次借本机浏览器登录态 (VMB_COOKIES_BROWSER, 本机/桌面场景)。"""
        cookies_file = os.getenv("VMB_COOKIES_FILE", "").strip()
        if cookies_file:
            if not Path(cookies_file).exists():
                logger.warning(f"VMB_COOKIES_FILE 不存在: {cookies_file}, 忽略 cookies")
            else:
                return ["--cookies", cookies_file]
        if self._cookies_browser:
            return ["--cookies-from-browser", self._cookies_browser]
        return []

    def _download_raw_audio(self, url: str, tmp_dir: Path) -> Path | None:
        """原生 bestaudio 直下 (无后处理, 不依赖 ffmpeg)。"""
        output_template = str(tmp_dir / "%(id)s.%(ext)s")
        cmd = [
            self._ytdlp or _YTDLP_CMD,
            "-f", "bestaudio/best",
            "--no-playlist",
            "--output", output_template,
            *self._cookies_args(),
            url,
        ]
        try:
            timeout = float(os.getenv("VMB_DOWNLOAD_TIMEOUT", "300"))
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode != 0:
                logger.warning(f"yt-dlp 原生音频下载失败 rc={result.returncode}: {result.stderr.strip()[-200:]}")
                return None
            return self._find_audio_file(result, tmp_dir)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"yt-dlp 原生音频下载异常: {e}")
            return None

    def _download_with_transcode(self, url: str, tmp_dir: Path, ffmpeg: str) -> Path | None:
        """--extract-audio + --ffmpeg-location 转码下载 (兜底)。"""
        output_template = str(tmp_dir / "%(id)s.%(ext)s")
        cmd = [
            self._ytdlp or _YTDLP_CMD,
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--no-playlist",
            "--output", output_template,
            "--ffmpeg-location", ffmpeg,
            *self._cookies_args(),
            url,
        ]
        try:
            timeout = float(os.getenv("VMB_DOWNLOAD_TIMEOUT", "300"))
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode != 0:
                logger.warning(f"yt-dlp 转码下载失败 rc={result.returncode}: {result.stderr.strip()[-200:]}")
                return None
            return self._find_audio_file(result, tmp_dir)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"yt-dlp 转码下载异常: {e}")
            return None

    @staticmethod
    def _find_audio_file(result: subprocess.CompletedProcess, tmp_dir: Path) -> Path | None:
        """定位下载的音频/视频文件。

        以目录真实落盘为准 (--print filename 对抖音等格式打印的推断路径不可靠),
        后缀覆盖 faster-whisper/PyAV 可解码的常见容器。
        """
        suffixes = (".mp3", ".m4a", ".wav", ".aac", ".opus", ".webm", ".mp4", ".m4s", ".flac", ".ogg")

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

    def _get_metadata(self, url: str) -> dict[str, Any]:
        cmd = [
            self._ytdlp or _YTDLP_CMD, "--dump-json", "--skip-download", url,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60.0,
            )
            if result.returncode == 0:
                line = result.stdout.strip().split("\n")[0]
                if line.startswith("{"):
                    import json
                    return dict(json.loads(line))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return {}


register_extractor("ytdlp_asr", YtDlpASRExtractor)