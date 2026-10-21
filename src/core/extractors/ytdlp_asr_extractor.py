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
import re
import tempfile
from pathlib import Path
from typing import Any

from ...utils.platform_detector import detect_platform
from ..asr import (
    AsrChainError,
    MediaRef,
    TranscribeOptions,
    transcribe_with_chain,
    transcript_to_extract_result,
)
from ..media import MediaFetchError, YtDlpMediaFetcher
from ..models import CostTier, ExtractOptions, ExtractResult
from ..platforms.rate_limit import get_platform_rate_limiter
from . import register_extractor
from .base import ContentExtractor

logger = logging.getLogger(__name__)


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
        self._fetcher = YtDlpMediaFetcher()
        self._available: bool | None = None

    def is_available(self) -> bool:
        """yt-dlp 可执行即可用 (本地 whisper 免费零 key, 不依赖云凭证)"""
        if self._available is None:
            self._available = self._fetcher.is_available()
        return self._available

    def extract(self, url: str, options: ExtractOptions | None = None) -> ExtractResult:
        platform = detect_platform(url)
        limiter = get_platform_rate_limiter()
        if (
            limiter.enabled
            and platform != "unknown"
            and limiter.circuit_state(platform) == "open"
        ):
            return ExtractResult(
                success=False, platform=platform, title="", content="",
                source="ytdlp_asr", url=url, cost_tier=CostTier.CHEAP,
                error=f"{platform} 平台熔断中，跳过 yt-dlp+ASR 兜底",
            )

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

            # ── ASR 降级链: 本地 faster-whisper → 阿里云 → DashScope ────────
            try:
                transcript = transcribe_with_chain(
                    MediaRef(path=audio_path),
                    TranscribeOptions(
                        language=options.asr_language if options else None,
                        max_cost=options.asr_max_cost if options else None,
                    ),
                    chain=options.asr_chain if options else None,
                )
            except AsrChainError as chain_err:
                logger.warning(f"ytdlp_asr 全链路失败: {chain_err}")
                transcript = None

            if transcript is not None:
                if transcript.provider == "faster-whisper":
                    source = "ytdlp_asr_local"
                elif transcript.provider == "aliyun":
                    source = "aliyun_asr"
                else:
                    source = "ytdlp_asr"
                return transcript_to_extract_result(
                    transcript,
                    url=url,
                    platform=platform,
                    title=title or audio_path.stem,
                    source=source,
                    cost_tier=CostTier.CHEAP,
                    duration_seconds=duration,
                    metadata={"platform_meta": metadata},
                )

            # ── 全部 ASR 不可用: 占位结果 ─────────────────────────────────
            return ExtractResult(
                success=True,
                platform=platform,
                title=title,
                content=(
                    "[yt-dlp+ASR] 已下载音频但 ASR 全链路不可用\n"
                    "可选: 安装 faster-whisper (pip install faster-whisper), "
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
                completeness="none",
                method="asr",
            )

    # ─────────────────────────── 下载/元信息 ───────────────────────────

    def _download_audio(self, url: str, tmp_dir: Path) -> Path | None:
        """下载音频（实际下载/转码/cookies 由 YtDlpMediaFetcher 负责）。"""
        try:
            return self._fetcher.fetch(url, tmp_dir).path
        except MediaFetchError as exc:
            logger.warning(f"yt-dlp 下载失败: {exc}")
            return None

    def _get_metadata(self, url: str) -> dict[str, Any]:
        return self._fetcher.dump_metadata(url)


register_extractor("ytdlp_asr", YtDlpASRExtractor)
