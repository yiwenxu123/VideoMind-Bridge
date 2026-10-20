"""ASR 链路行为基线测试（阶段 0.1 建立，阶段 1 迁移统一链后更新）

锁定三个调用点的语义契约：source 命名、content/segments 映射、
metadata 兼容键（api_provider/model）、失败时"落回页面/占位"的行为。
阶段 1 允许新增字段（asr_provider 等），不允许丢字段或改降级语义。
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from src.core.asr import AsrChainError, Segment, Transcript
from src.core.extractors import bilibili_extractor as bilibili_mod
from src.core.extractors import tikhub_extractor as tikhub_mod
from src.core.extractors import ytdlp_asr_extractor as ytdlp_mod
from src.core.extractors.bilibili_extractor import BilibiliExtractor
from src.core.extractors.tikhub_extractor import TikhubExtractor
from src.core.models import CostTier


@pytest.fixture(autouse=True)
def _clean_asr_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """避免开发者本机环境变量影响基线断言。"""
    monkeypatch.delenv("VMB_WHISPER_MODEL", raising=False)
    monkeypatch.delenv("VMB_ASR_LANGUAGE", raising=False)


@pytest.fixture
def audio_file(tmp_path: Path) -> Path:
    path = tmp_path / "audio.m4s"
    path.write_bytes(b"x" * 2048)
    return path


def _long_text(prefix: str) -> str:
    return prefix * 20


# ============================================================
# ytdlp_asr：本地 -> 云端 -> 占位（链由 src.core.asr 统一执行）
# ============================================================

def _make_ytdlp(monkeypatch: pytest.MonkeyPatch, audio_file: Path) -> ytdlp_mod.YtDlpASRExtractor:
    ext = ytdlp_mod.YtDlpASRExtractor()
    monkeypatch.setattr(ext, "is_available", lambda: True)
    monkeypatch.setattr(ext, "_download_audio", lambda url, tmp_dir: audio_file)
    monkeypatch.setattr(
        ext,
        "_get_metadata",
        lambda url: {"platform": "bilibili", "title": "基线视频", "duration": 120},
    )
    return ext


def test_ytdlp_asr_local_source_and_mapping(monkeypatch, audio_file):
    ext = _make_ytdlp(monkeypatch, audio_file)
    transcript = Transcript(
        text=_long_text("本地转写"),
        provider="faster-whisper",
        model="base",
        language="zh",
        segments=[Segment(start=0.0, end=1.5, text="本地转写")],
        cost_tier=CostTier.CHEAP,
    )
    monkeypatch.setattr(ytdlp_mod, "transcribe_with_chain", lambda media, options: transcript)

    result = ext.extract("https://www.bilibili.com/video/BV1xx")

    assert result.success is True
    assert result.source == "ytdlp_asr_local"
    assert result.content == transcript.text
    assert result.language == "zh"
    assert result.segments == [{"start": 0.0, "end": 1.5, "text": "本地转写"}]
    assert result.metadata["api_provider"] == "faster_whisper"
    assert result.metadata["model"] == "base"
    assert result.metadata["asr_provider"] == "faster-whisper"
    assert result.metadata["platform_meta"]["title"] == "基线视频"


def test_ytdlp_asr_aliyun_source_preserved(monkeypatch, audio_file):
    ext = _make_ytdlp(monkeypatch, audio_file)
    transcript = Transcript(
        text=_long_text("阿里云转写"),
        provider="aliyun",
        model="paraformer-v2",
        language="zh",
        segments=[Segment(start=0.0, end=2.0, text="阿里云转写")],
        cost_tier=CostTier.EXPENSIVE,
    )
    monkeypatch.setattr(ytdlp_mod, "transcribe_with_chain", lambda media, options: transcript)

    result = ext.extract("https://www.bilibili.com/video/BV1xx")

    assert result.source == "aliyun_asr"
    assert result.metadata["api_provider"] == "aliyun_asr"
    assert result.metadata["model"] == "paraformer-v2"


def test_ytdlp_asr_placeholder_when_chain_fails(monkeypatch, audio_file):
    ext = _make_ytdlp(monkeypatch, audio_file)

    def _raise(*args, **kwargs):
        raise AsrChainError([{"provider": "faster_whisper", "status": "unavailable"}])

    monkeypatch.setattr(ytdlp_mod, "transcribe_with_chain", _raise)

    result = ext.extract("https://www.bilibili.com/video/BV1xx")

    assert result.success is True
    assert result.is_placeholder is True
    assert "ASR 全链路不可用" in result.content
    assert result.metadata["asr_available"] is False
    assert result.metadata["platform_meta"]["title"] == "基线视频"


# ============================================================
# B站：链成功 → bilibili_asr；链失败 → None（落回页面正文）
# ============================================================

def _bili_playurl() -> dict:
    return {
        "audio_urls": ["https://cdn.example/audio.m4s"],
        "title": "B站基线视频",
        "duration": 180,
        "platform": "bilibili",
        "ext": ".m4s",
    }


def test_bilibili_asr_source_and_mapping(audio_file):
    ext = BilibiliExtractor()
    transcript = Transcript(
        text=_long_text("B站本地转写"),
        provider="faster-whisper",
        model="base",
        language="zh",
        segments=[Segment(start=0.0, end=1.0, text="B站本地转写")],
    )
    with (
        mock.patch.object(BilibiliExtractor, "get_playurl_audio_urls", return_value=_bili_playurl()),
        mock.patch.object(BilibiliExtractor, "_download_audio", return_value=audio_file),
        mock.patch.object(bilibili_mod, "transcribe_with_chain", return_value=transcript),
    ):
        result = ext._try_audio_asr_fallback(
            "https://www.bilibili.com/video/BV1xx", "BV1xx", "B站基线视频", 180
        )

    assert result is not None
    assert result.success is True
    assert result.source == "bilibili_asr"
    assert result.language == "zh"
    assert result.segments == [{"start": 0.0, "end": 1.0, "text": "B站本地转写"}]
    assert result.metadata["bvid"] == "BV1xx"
    assert result.metadata["api_provider"] == "faster_whisper"
    assert result.metadata["model"] == "base"


def test_bilibili_dashscope_maps_legacy_provider(audio_file):
    ext = BilibiliExtractor()
    transcript = Transcript(
        text=_long_text("B站云端转写"),
        provider="dashscope",
        model="paraformer-v2",
        language="zh",
    )
    with (
        mock.patch.object(BilibiliExtractor, "get_playurl_audio_urls", return_value=_bili_playurl()),
        mock.patch.object(BilibiliExtractor, "_download_audio", return_value=audio_file),
        mock.patch.object(bilibili_mod, "transcribe_with_chain", return_value=transcript),
    ):
        result = ext._try_audio_asr_fallback(
            "https://www.bilibili.com/video/BV1xx", "BV1xx", "B站基线视频", 180
        )

    assert result is not None
    assert result.source == "bilibili_asr"
    assert result.metadata["api_provider"] == "dashscope_asr"
    assert result.metadata["model"] == "paraformer-v2"


def test_bilibili_returns_none_when_chain_fails(audio_file):
    ext = BilibiliExtractor()
    with (
        mock.patch.object(BilibiliExtractor, "get_playurl_audio_urls", return_value=_bili_playurl()),
        mock.patch.object(BilibiliExtractor, "_download_audio", return_value=audio_file),
        mock.patch.object(
            bilibili_mod,
            "transcribe_with_chain",
            side_effect=AsrChainError([{"provider": "faster_whisper", "status": "asr_failed"}]),
        ),
    ):
        result = ext._try_audio_asr_fallback(
            "https://www.bilibili.com/video/BV1xx", "BV1xx", "B站基线视频", 180
        )

    assert result is None


# ============================================================
# TikHub：链成功 → tikhub_asr；链失败 → 占位
# ============================================================

def test_tikhub_asr_source_and_mapping(audio_file):
    ext = TikhubExtractor()
    url = "https://www.douyin.com/video/123"
    transcript = Transcript(
        text=_long_text("TikHub 本地转写"),
        provider="faster-whisper",
        model="base",
        language="zh",
        segments=[Segment(start=0.0, end=1.0, text="TikHub 本地转写")],
    )
    with (
        mock.patch.object(TikhubExtractor, "_download_audio", return_value=audio_file),
        mock.patch.object(tikhub_mod, "transcribe_with_chain", return_value=transcript),
    ):
        result = ext._try_download_and_transcribe("https://cdn.example/video.mp4", url, "douyin", "标题", 60)

    assert result is not None
    assert result.success is True
    assert result.source == "tikhub_asr"
    assert result.segments == [{"start": 0.0, "end": 1.0, "text": "TikHub 本地转写"}]
    assert result.metadata["api_provider"] == "faster_whisper"
    assert result.metadata["model"] == "base"


def test_tikhub_placeholder_when_chain_fails(audio_file):
    ext = TikhubExtractor()
    url = "https://www.douyin.com/video/123"
    with (
        mock.patch.object(TikhubExtractor, "_download_audio", return_value=audio_file),
        mock.patch.object(
            tikhub_mod,
            "transcribe_with_chain",
            side_effect=AsrChainError([{"provider": "faster_whisper", "status": "unavailable"}]),
        ),
    ):
        result = ext._try_download_and_transcribe("https://cdn.example/video.mp4", url, "douyin", "标题", 60)

    assert result is not None
    assert result.success is True
    assert result.is_placeholder is True
    assert result.source == "tikhub_asr"
    assert result.content == ""
    assert result.metadata["asr_available"] is False
    assert result.error == "音频已下载但无可用 ASR 转写"
