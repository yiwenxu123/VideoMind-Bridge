"""yt-dlp + ASR 组合提取器

下载视频音频后通过语音识别转写文字，作为无字幕视频的通用兜底。
优先级在平台原生提取器之后，TikHub 付费 API 之前。

工作流程:
  1. yt-dlp 下载视频/音频
  2. ffmpeg 提取音频 (如果下载的是视频)
  3. 阿里云 ASR (paraformer-v2) 转写 (已配置时)
  4. 未配置 ASR 时返回音频路径信息

成本: CHEAP (阿里云 ASR ~0.00008元/秒, 10分钟视频约0.048元)
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..models import CostTier, ExtractResult
from . import register_extractor
from ._dashscope_asr import transcribe_audio_data
from .aliyun_asr_extractor import AliyunASRExtractor
from .base import ContentExtractor

logger = logging.getLogger(__name__)

_YTDLP_CMD = "yt-dlp"

_SUPPORTED_PLATFORMS = [
    "bilibili", "douyin", "xiaohongshu", "youtube",
    "tiktok", "twitter", "x.com", "instagram", "ted",
]


class YtDlpASRExtractor(ContentExtractor):
    """yt-dlp + 阿里云 ASR 组合提取器 (无字幕视频通用兜底)"""

    platform_name = "ytdlp_asr"
    _cost_tier = CostTier.CHEAP
    url_pattern = re.compile(
        r"(youtube\.com|youtu\.be|bilibili\.com|b23\.tv|"
        r"douyin\.com|iesdouyin\.com|xiaohongshu\.com|xhslink\.com|"
        r"twitter\.com|x\.com|tiktok\.com|instagram\.com|ted\.com)"
    )

    def __init__(self) -> None:
        self._asr = AliyunASRExtractor()
        self._available: bool | None = None

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            subprocess.run(
                [_YTDLP_CMD, "--version"],
                capture_output=True, text=True, timeout=10.0,
            )
            self._available = True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._available = False
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
                    error="yt-dlp 下载音频失败",
                )

            metadata = self._get_metadata(url)

            # 优先阿里云 NLS ASR, 未配置时回退 DashScope (复用 coze_ali_key)
            if self._asr.is_available():
                result = self._asr.transcribe_audio(audio_path)
            else:
                dashscope_key = self._resolve_api_key("coze_ali_key")
                if dashscope_key:
                    result = self._transcribe_dashscope(
                        audio_path, dashscope_key, url,
                        metadata.get("platform", "video"),
                        metadata.get("title", ""),
                        float(metadata.get("duration", 0)),
                    )
                else:
                    result = None

            if result and result.success:
                result.url = url
                if not result.title or result.title == audio_path.stem:
                    result.title = metadata.get("title", audio_path.stem)
                return result

            if result and result.error:
                logger.warning(f"ytdlp_asr 转写失败: {result.error}")

            return ExtractResult(
                success=True,
                platform=metadata.get("platform", "video"),
                title=metadata.get("title", audio_path.stem),
                content=(
                    "[yt-dlp+ASR] 已下载音频但 ASR 不可用\n"
                    "请配置 ALIYUN_ACCESS_KEY_ID / ACCESS_KEY_SECRET / APPKEY, "
                    "或 coze_ali_key (DashScope)\n"
                ),
                source="ytdlp_asr",
                url=url,
                cost_tier=CostTier.CHEAP,
                duration_seconds=float(metadata.get("duration", 0)),
                is_placeholder=True,
                metadata={
                    "audio_path": str(audio_path),
                    "asr_available": False,
                    "platform_meta": metadata,
                },
            )

    def _transcribe_dashscope(
        self, audio_path: Path, api_key: str, url: str,
        platform: str, title: str, duration: float,
    ) -> ExtractResult:
        """DashScope paraformer-v2 转写 (复用 coze_ali_key, 免额外配置)"""
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

    def _download_audio(self, url: str, tmp_dir: Path) -> Path | None:
        output_template = str(tmp_dir / "%(id)s.%(ext)s")

        cmd = [
            _YTDLP_CMD,
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--output", output_template,
            "--print", "filename",
            url,
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300.0,
            )

            if result.returncode != 0:
                return None

            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line:
                    candidate = Path(line)
                    if candidate.exists() and candidate.suffix in (".mp3", ".m4a", ".wav", ".aac"):
                        return candidate

            mp3_files = list(tmp_dir.glob("*.mp3"))
            if mp3_files:
                return mp3_files[0]

            audio_files = list(tmp_dir.glob("*"))
            audio_files = [f for f in audio_files if f.suffix in (".mp3", ".m4a", ".wav", ".aac", ".opus")]
            if audio_files:
                return audio_files[0]

            return None

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    @staticmethod
    def _get_metadata(url: str) -> dict[str, Any]:
        cmd = [
            _YTDLP_CMD, "--dump-json", "--skip-download", url,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30.0,
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
