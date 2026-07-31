"""Tikhub.io 商业 API 提取器

提供 1000+ API 覆盖 16+ 平台 (抖音/B站/小红书/Instagram/Twitter 等)。
需要 TIKHUB_API_KEY 环境变量或配置文件中的 api_key。

认证: Authorization: Bearer {token}
成本: ~$0.001/请求

TikHub 返回视频元数据和 CDN 下载地址。
优先尝试下载音频+DashScope paraformer ASR 转写；
ASR 不可用时返回元数据+下载链接。
"""

from __future__ import annotations

import base64
import re
import subprocess
import tempfile
from pathlib import Path

import httpx

from ..models import CostTier, ExtractResult
from . import register_extractor
from .base import ContentExtractor

TIKHUB_API_BASE = "https://api.tikhub.io"
_FFMPEG_CMD = "ffmpeg"

PLATFORM_ENDPOINTS: dict[str, dict] = {
    "douyin": {
        "endpoint": "/api/v1/douyin/web/fetch_one_video_by_share_url",
        "params_fn": lambda url: {"share_url": url},
    },
    "bilibili": {
        "endpoint": "/api/v1/bilibili/web/fetch_one_video",
        "params_fn": lambda url: {"bv_id": re.search(r"BV\w+", url).group(0) if re.search(r"BV\w+", url) else ""},
    },
    "xiaohongshu": {
        "endpoint": "/api/v1/xiaohongshu/web_v3/fetch_note_detail",
        "params_fn": lambda url: {"note_id": url.split("/")[-1].split("?")[0], "xsec_token": ""},
    },
    "tiktok": {
        "endpoint": "/api/v1/tiktok/web/fetch_one_video",
        "params_fn": lambda url: {"share_url": url},
    },
    "youtube": {
        "endpoint": "/api/v1/youtube/web/fetch_one_video",
        "params_fn": lambda url: {"url": url},
    },
    "instagram": {
        "endpoint": "/api/v1/instagram/web/fetch_post_info",
        "params_fn": lambda url: {"url": url},
    },
    "twitter": {
        "endpoint": "/api/v1/twitter/web/fetch_tweet_info",
        "params_fn": lambda url: {"url": url},
    },
}

_SUPPORTED_PLATFORMS = {
    "douyin": re.compile(r"douyin\.com|iesdouyin\.com"),
    "bilibili": re.compile(r"bilibili\.com|b23\.tv"),
    "xiaohongshu": re.compile(r"xiaohongshu\.com|xhslink\.com"),
    "tiktok": re.compile(r"tiktok\.com"),
    "instagram": re.compile(r"instagram\.com"),
    "twitter": re.compile(r"twitter\.com|x\.com"),
    "youtube": re.compile(r"youtube\.com|youtu\.be"),
    "weibo": re.compile(r"weibo\.com"),
}


def _detect_commercial_platform(url: str) -> str | None:
    """委托统一的平台检测器, 再过滤到 TikHub 支持的平台集"""
    from ...utils.platform_detector import detect_platform
    platform = detect_platform(url)
    if platform in _SUPPORTED_PLATFORMS:
        return platform
    return None


def _extract_text(data: dict, *keys: str) -> str:
    for key in keys:
        if isinstance(key, str) and "." in key:
            parts = key.split(".")
            val = data
            for part in parts:
                if isinstance(val, dict):
                    val = val.get(part, "")
                else:
                    val = ""
                    break
            if val:
                return str(val)
        else:
            val = data.get(key, "")
            if val:
                return str(val)
    return ""


def _get_download_url(aweme: dict) -> str | None:
    video = aweme.get("video", {}) or {}
    for src in ("download_addr", "play_addr"):
        urls = video.get(src, {}).get("url_list", []) or []
        for u in urls:
            if u and u.startswith("http"):
                return u
    return None


class TikhubExtractor(ContentExtractor):
    """Tikhub.io 商业 API 提取器"""

    platform_name = "tikhub"
    _cost_tier = CostTier.PREMIUM
    url_pattern = re.compile(r"|".join(p.pattern for p in _SUPPORTED_PLATFORMS.values()))

    def __init__(self) -> None:
        self._api_key: str | None = None
        self._client = httpx.Client(
            timeout=60.0,
            headers={"User-Agent": "VideoMind-Bridge/1.0"},
            follow_redirects=True,
        )

    def is_available(self) -> bool:
        key = self._resolve_api_key("tikhub")
        self._api_key = key.strip() if key and key.strip() else None
        return self._api_key is not None

    def supports(self, url: str) -> bool:
        return bool(self.url_pattern.search(url))

    def extract(self, url: str) -> ExtractResult:
        platform = _detect_commercial_platform(url)
        if not platform:
            return ExtractResult(
                success=False, platform="unknown", title="", content="",
                source="tikhub", url=url, cost_tier=self._cost_tier,
                error="tikhub 不支持此 URL",
            )

        if not self._api_key:
            return ExtractResult(
                success=False, platform=platform, title="", content="",
                source="tikhub", url=url, cost_tier=self._cost_tier,
                error="TIKHUB_API_KEY 未配置",
            )

        try:
            result_json = self._call_api(url, platform)
            return self._parse_response(result_json, url, platform)
        except Exception as e:
            return ExtractResult(
                success=False, platform=platform, title="", content="",
                source="tikhub", url=url, cost_tier=self._cost_tier,
                error=f"Tikhub API 调用失败: {e}",
            )

    def _call_api(self, url: str, platform: str) -> dict:
        config = PLATFORM_ENDPOINTS.get(platform)
        if not config:
            return {"data": {}}

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

        resp = self._client.get(
            f"{TIKHUB_API_BASE}{config['endpoint']}",
            params=config["params_fn"](url),
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

    def _parse_response(self, data: dict, url: str, platform: str) -> ExtractResult:
        raw_data = data.get("data") or {}
        aweme = raw_data.get("aweme_detail")
        if not isinstance(aweme, dict):
            aweme = raw_data.get("data") if isinstance(raw_data.get("data"), dict) else raw_data
        title = _extract_text(aweme, "title", "desc", "share_info.share_title", "description")
        desc_val = aweme.get("desc", "") or ""
        duration_val = aweme.get("duration", 0) or 0
        duration = float(duration_val) if duration_val else 0.0

        download_url = _get_download_url(aweme)

        if download_url:
            audio_result = self._try_download_and_transcribe(download_url, url, platform, title, duration)
            if audio_result and audio_result.success and audio_result.content:
                return audio_result

        metadata = {
            "api_provider": "tikhub.io",
            "download_url": download_url,
        }

        return ExtractResult(
            success=bool(desc_val),
            platform=platform,
            title=title or "TikHub 提取结果",
            content=desc_val or (f"[TikHub] 已获取下载地址，但未配置 ASR\n下载地址: {download_url}" if download_url else ""),
            source="tikhub",
            url=url,
            cost_tier=self._cost_tier,
            duration_seconds=duration,
            metadata=metadata,
        )

    def _try_download_and_transcribe(
        self, download_url: str, url: str, platform: str,
        title: str, duration: float,
    ) -> ExtractResult | None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = self._download_audio(download_url, Path(tmp_dir))
            if not audio_path or audio_path.stat().st_size < 1000:
                return None

            result = self._transcribe_local(audio_path, url, platform, title, duration)
            if result.success and result.content:
                return result

            dashscope_key = self._resolve_api_key("coze_ali_key")
            if dashscope_key:
                result = self._transcribe_with_dashscope(audio_path, dashscope_key, url, platform, title, duration)
                if result.success and result.content:
                    return result

            from .aliyun_asr_extractor import AliyunASRExtractor
            asr = AliyunASRExtractor()
            if asr.is_available():
                result = asr.transcribe_audio(audio_path)
                result.url = url
                result.platform = platform
                if not result.title or result.title == audio_path.stem:
                    result.title = title or audio_path.stem
                result.source = "tikhub_asr"
                return result

            return ExtractResult(
                success=True,
                platform=platform,
                title=title or "TikHub 提取结果",
                content="",
                source="tikhub_asr",
                url=url,
                cost_tier=self._cost_tier,
                duration_seconds=duration,
                is_placeholder=True,
                metadata={
                    "audio_path": str(audio_path),
                    "asr_available": False,
                    "api_provider": "tikhub.io",
                },
                error="音频已下载但无可用 ASR 转写",
            )

    def _transcribe_local(self, audio_path: Path, url: str, platform: str, title: str, duration: float) -> ExtractResult:
        try:
            import os as _os
            _os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            from faster_whisper import WhisperModel
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, info = model.transcribe(str(audio_path), language="zh")

            text_parts = []
            segment_list = []
            for seg in segments:
                text_parts.append(seg.text)
                segment_list.append({
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                })

            full_text = " ".join(text_parts)
            seg_count = len(segment_list)

            if not full_text:
                return ExtractResult(
                    success=False, platform=platform, title=title, content="",
                    source="tikhub_asr", url=url, cost_tier=self._cost_tier,
                    error="Whisper ASR 返回了空转录",
                )

            return ExtractResult(
                success=True, platform=platform,
                title=title or audio_path.stem,
                content=full_text,
                source="tikhub_asr", url=url,
                cost_tier=self._cost_tier,
                duration_seconds=duration or (segment_list[-1]["end"] if segment_list else 0),
                language=info.language if info else "zh",
                segments=segment_list,
                metadata={"api_provider": "faster_whisper", "model": "small", "segments": seg_count},
            )
        except ImportError:
            return ExtractResult(
                success=False, platform=platform, title=title, content="",
                source="tikhub_asr", url=url, cost_tier=self._cost_tier,
                error="faster-whisper 未安装",
            )
        except Exception as e:
            return ExtractResult(
                success=False, platform=platform, title=title, content="",
                source="tikhub_asr", url=url, cost_tier=self._cost_tier,
                error=f"Whisper ASR 失败: {e}",
            )

    def _transcribe_with_dashscope(
        self, audio_path: Path, api_key: str, url: str,
        platform: str, title: str, duration: float,
    ) -> ExtractResult:
        audio_data = audio_path.read_bytes()
        audio_b64 = base64.b64encode(audio_data).decode()

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "paraformer-v2",
            "input": {"audio_data": audio_b64},
        }

        try:
            resp = httpx.post(
                "https://dashscope.aliyuncs.com/api/v1/services/audio/transcription/asr",
                headers=headers, json=payload, timeout=180.0,
            )
            resp.raise_for_status()
            data = resp.json()

            output = data.get("output", {})
            text = output.get("text", "") or output.get("transcript", "") or ""
            segments_raw = output.get("sentences", output.get("segments", []))

            segments = [
                {"start": s.get("begin_time", s.get("start", 0)) / 1000,
                 "end": s.get("end_time", s.get("end", 0)) / 1000,
                 "text": s.get("text", "")}
                for s in segments_raw if s.get("text")
            ] if isinstance(segments_raw, list) else None

            return ExtractResult(
                success=bool(text),
                platform=platform,
                title=title or audio_path.stem,
                content=text or "DashScope ASR 返回了空转录",
                source="tikhub_asr",
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
                platform=platform, title=title or "TikHub 提取",
                content="",
                source="tikhub_asr", url=url, cost_tier=self._cost_tier,
                duration_seconds=duration,
                error=f"DashScope ASR 调用失败: {e}",
            )

    def _download_audio(self, url: str, tmp_dir: Path) -> Path | None:
        temp_file = tmp_dir / "video.mp4"
        try:
            resp = self._client.get(url, timeout=300.0)
            resp.raise_for_status()
            temp_file.write_bytes(resp.content)
        except Exception:
            return None

        audio_path = tmp_dir / "audio.mp3"
        try:
            subprocess.run(
                [_FFMPEG_CMD, "-y", "-i", str(temp_file), "-vn", "-acodec", "libmp3lame", str(audio_path)],
                capture_output=True, text=True, timeout=120.0, check=True,
            )
            return audio_path if audio_path.exists() else None
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            return None


register_extractor("tikhub", TikhubExtractor)
