"""阿里云 ASR 提取器

使用阿里云语音识别 (paraformer-v2) 为无字幕视频生成转录。
需要配置阿里云 AccessKey:
  - ALIYUN_ACCESS_KEY_ID
  - ALIYUN_ACCESS_KEY_SECRET
  - ALIYUN_APPKEY (项目 AppKey)

成本: 按量计费, paraformer-v2 约 0.5 元/小时
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

import httpx

from ..models import CostTier, ExtractResult
from . import register_extractor
from .base import ContentExtractor

# 阿里云语音识别 API
ALIYUN_ASR_ENDPOINT = "https://nls-meta.cn-shanghai.aliyuncs.com"
ALIYUN_ASR_GATEWAY = "wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1"


class AliyunASRExtractor(ContentExtractor):
    """阿里云 ASR 提取器 (无字幕视频兜底)"""

    platform_name = "aliyun_asr"
    _cost_tier = CostTier.EXPENSIVE
    url_pattern = re.compile(r"https?://")  # 通用, 配合 should_try 使用

    def __init__(self) -> None:
        ak = self._resolve_api_key("aliyun_access_key_id")
        aks = self._resolve_api_key("aliyun_access_key_secret")
        apk = self._resolve_api_key("aliyun_appkey")
        self._access_key = ak.strip() if ak and ak.strip() else ""
        self._access_secret = aks.strip() if aks and aks.strip() else ""
        self._appkey = apk.strip() if apk and apk.strip() else ""
        self._client = httpx.Client(timeout=30.0)

    def is_available(self) -> bool:
        return bool(self._access_key and self._access_secret and self._appkey)

    def supports(self, url: str) -> bool:
        return bool(self.url_pattern.search(url))

    def should_try(self, url: str, max_cost: CostTier | None = None) -> bool:
        if not super().should_try(url, max_cost):
            return False
        # ASR 提取器只在其他方式均失败时作为兜底
        # 实际路由层通过 max_cost 和优先级控制
        return True

    def extract(self, url: str) -> ExtractResult:
        # Aliyun ASR 需要音频文件路径作为输入, 而非 URL
        # 此提取器通常会收到一个已下载的音频 URL 或文件路径
        # 在 v2 引擎中, 它会由 yt-dlp 先下载音频后调用
        return ExtractResult(
            success=False,
            platform="unknown",
            title="",
            content="",
            source="aliyun_asr",
            url=url,
            cost_tier=self._cost_tier,
            error=(
                "阿里云 ASR 提取器需要先下载音频文件。"
                "使用 --cost-tier expensive 或 --smart 时, "
                "路由层会自动先通过 yt-dlp 下载音频再调用 ASR。"
            ),
        )

    def transcribe_audio(self, audio_path: Path, file_url: str = "") -> ExtractResult:
        """转录音频文件 (通过阿里云 paraformer-v2 API)

        Args:
            audio_path: 本地音频文件路径
            file_url: 可公开访问的音频 URL (二选一)

        Returns:
            ExtractResult: 转录结果
        """
        if not self.is_available():
            return ExtractResult(
                success=False, platform="unknown", title="", content="",
                source="aliyun_asr", url=str(audio_path), cost_tier=self._cost_tier,
                error="阿里云 ASR 未配置: 需要 ALIYUN_ACCESS_KEY_ID/ACCESS_KEY_SECRET/APPKEY",
            )

        try:
            return self._call_asr_api(audio_path, file_url)
        except Exception as e:
            return ExtractResult(
                success=False, platform="unknown", title="", content="",
                source="aliyun_asr", url=str(audio_path), cost_tier=self._cost_tier,
                error=f"阿里云 ASR 调用失败: {e}",
            )

    def _call_asr_api(self, audio_path: Path, file_url: str) -> ExtractResult:
        """调用阿里云语音识别 RESTful API"""
        audio_data = audio_path.read_bytes()
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
        audio_format = audio_path.suffix.lstrip(".") or "mp3"
        if audio_format == "m4a":
            audio_format = "mp4"

        payload = {
            "appkey": self._appkey,
            "format": audio_format,
            "sample_rate": 16000,
            "enable_punctuation_prediction": True,
            "enable_inverse_text_normalization": True,
            "enable_voice_detection": False,
            "audio_data": audio_b64,
        }

        resp = self._client.post(
            f"{ALIYUN_ASR_ENDPOINT}/rest/v1/asr/recognize",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-Access-Key-Id": self._access_key,
                "X-Access-Key-Secret": self._access_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != 0:
            return ExtractResult(
                success=False, platform="unknown", title="", content="",
                source="aliyun_asr", url=str(audio_path), cost_tier=self._cost_tier,
                error=f"阿里云 ASR 返回错误: {data.get('message', '未知错误')}",
            )

        sentences = data.get("result", {}).get("sentences", [])
        full_text = "".join(s.get("text", "") for s in sentences)
        segments = [
            {"start": s.get("begin_time", 0) / 1000, "end": s.get("end_time", 0) / 1000, "text": s.get("text", "")}
            for s in sentences
        ]

        return ExtractResult(
            success=True,
            platform="unknown",
            title=audio_path.stem,
            content=full_text or "阿里云 ASR 返回了空转录",
            source="aliyun_asr",
            url=str(audio_path),
            cost_tier=self._cost_tier,
            duration_seconds=segments[-1]["end"] if segments else 0.0,
            language=data.get("result", {}).get("language", "zh"),
            segments=segments if segments else None,
            metadata={"api_provider": "aliyun_asr", "model": "paraformer-v2"},
        )


register_extractor("aliyun_asr", AliyunASRExtractor)
