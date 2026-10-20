"""阿里云 ASR 适配器（逻辑迁移自 extractors/aliyun_asr_extractor.py）

使用阿里云语音识别 (paraformer-v2) 为无字幕视频生成转录。
需要配置阿里云 AccessKey:
  - ALIYUN_ACCESS_KEY_ID
  - ALIYUN_ACCESS_KEY_SECRET
  - ALIYUN_APPKEY (项目 AppKey)

成本: 按量计费, paraformer-v2 约 0.5 元/小时
"""

from __future__ import annotations

import base64

import httpx

from ...models import CostTier
from ..base import Transcriber, resolve_extractor_key
from ..registry import register_transcriber
from ..types import (
    AsrEmpty,
    AsrFailed,
    AsrUnavailable,
    Capabilities,
    MediaRef,
    Segment,
    TranscribeOptions,
    Transcript,
)

ALIYUN_ASR_ENDPOINT = "https://nls-meta.cn-shanghai.aliyuncs.com"
ALIYUN_ASR_MODEL = "paraformer-v2"


class AliyunTranscriber(Transcriber):
    """阿里云 NLS paraformer-v2 后端（需三个 AccessKey）"""

    name = "aliyun"

    def _keys(self) -> tuple[str, str, str]:
        def _get(name: str) -> str:
            value = self.config.get(name) or resolve_extractor_key(name)
            return value.strip() if value and value.strip() else ""

        return _get("aliyun_access_key_id"), _get("aliyun_access_key_secret"), _get("aliyun_appkey")

    def capabilities(self) -> Capabilities:
        access_key, access_secret, appkey = self._keys()
        return Capabilities(
            name=self.name,
            available=bool(access_key and access_secret and appkey),
            languages=["zh"],
            timestamps=True,
            cost_tier=CostTier.EXPENSIVE,
            model=ALIYUN_ASR_MODEL,
            notes="按量计费，约 0.5 元/小时",
        )

    def transcribe(self, media: MediaRef, options: TranscribeOptions) -> Transcript:
        access_key, access_secret, appkey = self._keys()
        if not (access_key and access_secret and appkey):
            raise AsrUnavailable(
                "阿里云 ASR 未配置: 需要 ALIYUN_ACCESS_KEY_ID/ACCESS_KEY_SECRET/APPKEY"
            )
        audio_path = media.require_path()

        audio_format = audio_path.suffix.lstrip(".") or "mp3"
        if audio_format == "m4a":
            audio_format = "mp4"
        payload = {
            "appkey": appkey,
            "format": audio_format,
            "sample_rate": 16000,
            "enable_punctuation_prediction": True,
            "enable_inverse_text_normalization": True,
            "enable_voice_detection": False,
            "audio_data": base64.b64encode(audio_path.read_bytes()).decode("utf-8"),
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{ALIYUN_ASR_ENDPOINT}/rest/v1/asr/recognize",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Access-Key-Id": access_key,
                        "X-Access-Key-Secret": access_secret,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            raise AsrFailed(f"阿里云 ASR 调用失败: {exc}") from exc

        if data.get("status") != 0:
            raise AsrFailed(f"阿里云 ASR 返回错误: {data.get('message', '未知错误')}")

        sentences = data.get("result", {}).get("sentences", [])
        text = "".join(s.get("text", "") for s in sentences).strip()
        if not text:
            raise AsrEmpty("阿里云 ASR 返回了空转录")

        segments = [
            Segment(
                start=s.get("begin_time", 0) / 1000,
                end=s.get("end_time", 0) / 1000,
                text=s.get("text", ""),
            )
            for s in sentences
        ]
        return Transcript(
            text=text,
            provider="aliyun",
            model=ALIYUN_ASR_MODEL,
            language=data.get("result", {}).get("language") or options.language or "zh",
            segments=segments or None,
            duration_seconds=segments[-1].end if segments else 0.0,
            cost_tier=CostTier.EXPENSIVE,
        )


register_transcriber("aliyun", AliyunTranscriber)
