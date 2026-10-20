"""ASR 链路行为基线测试（阶段 0.1）

锁定重构前 ytdlp_asr / B站 / TikHub 三条 ASR 路径的 source、content、
segments、metadata 与降级语义。阶段 1 迁移到统一 Transcriber 端口后，
这些断言应继续成立（允许新增字段，不允许丢字段或改语义）。
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from src.core.extractors import ytdlp_asr_extractor as ytdlp_mod
from src.core.extractors.bilibili_extractor import BilibiliExtractor
from src.core.extractors.tikhub_extractor import TikhubExtractor
from src.core.models import CostTier, ExtractResult


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
# ytdlp_asr：本地 -> 阿里云 -> DashScope -> 占位
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


def test_ytdlp_asr_local_success(monkeypatch, audio_file):
    ext = _make_ytdlp(monkeypatch, audio_file)
    local_result = ExtractResult(
        success=True,
        platform="bilibili",
        title="基线视频",
        content=_long_text("本地转写"),
        source="ytdlp_asr_local",
        url="https://www.bilibili.com/video/BV1xx",
        cost_tier=CostTier.CHEAP,
        duration_seconds=120,
        language="zh",
        segments=[{"start": 0.0, "end": 1.5, "text": "本地转写"}],
        metadata={"asr_provider": "faster-whisper", "model": "base"},
    )
    monkeypatch.setattr(ext, "_transcribe_local", lambda *a, **k: local_result)

    result = ext.extract("https://www.bilibili.com/video/BV1xx")

    assert result is local_result
    assert result.success is True
    assert result.source == "ytdlp_asr_local"
    assert result.metadata["asr_provider"] == "faster-whisper"
    assert result.metadata["model"] == "base"
    assert result.segments == [{"start": 0.0, "end": 1.5, "text": "本地转写"}]


def test_ytdlp_asr_falls_back_to_aliyun(monkeypatch, audio_file):
    ext = _make_ytdlp(monkeypatch, audio_file)
    monkeypatch.setattr(ext, "_transcribe_local", lambda *a, **k: None)

    aliyun_result = ExtractResult(
        success=True,
        platform="unknown",
        title="audio",
        content=_long_text("阿里云转写"),
        source="aliyun_asr",
        url=str(audio_file),
        cost_tier=CostTier.EXPENSIVE,
        language="zh",
        segments=[{"start": 0.0, "end": 2.0, "text": "阿里云转写"}],
        metadata={"api_provider": "aliyun_asr", "model": "paraformer-v2"},
    )
    with (
        mock.patch.object(ytdlp_mod.AliyunASRExtractor, "is_available", return_value=True),
        mock.patch.object(
            ytdlp_mod.AliyunASRExtractor,
            "transcribe_audio",
            return_value=aliyun_result,
        ),
    ):
        result = ext.extract("https://www.bilibili.com/video/BV1xx")

    assert result.success is True
    assert result.source == "aliyun_asr"
    assert result.content == _long_text("阿里云转写")
    assert result.url == "https://www.bilibili.com/video/BV1xx"
    assert result.metadata["api_provider"] == "aliyun_asr"
    assert result.metadata["model"] == "paraformer-v2"


def test_ytdlp_asr_returns_placeholder_when_all_backends_unavailable(monkeypatch, audio_file):
    ext = _make_ytdlp(monkeypatch, audio_file)
    monkeypatch.setattr(ext, "_transcribe_local", lambda *a, **k: None)
    monkeypatch.setattr(ext, "_resolve_api_key", lambda name: None)

    with mock.patch.object(ytdlp_mod.AliyunASRExtractor, "is_available", return_value=False):
        result = ext.extract("https://www.bilibili.com/video/BV1xx")

    assert result.success is True
    assert result.is_placeholder is True
    assert "ASR 全链路不可用" in result.content
    assert result.metadata["asr_available"] is False
    assert result.metadata["platform_meta"]["title"] == "基线视频"


# ============================================================
# B站：本地 -> DashScope -> None（落回页面正文）
# ============================================================

def _bili_playurl() -> dict:
    return {
        "audio_urls": ["https://cdn.example/audio.m4s"],
        "title": "B站基线视频",
        "duration": 180,
        "platform": "bilibili",
        "ext": ".m4s",
    }


def test_bilibili_asr_local_success(audio_file):
    ext = BilibiliExtractor()
    with (
        mock.patch.object(BilibiliExtractor, "get_playurl_audio_urls", return_value=_bili_playurl()),
        mock.patch.object(BilibiliExtractor, "_download_audio", return_value=audio_file),
        mock.patch(
            "src.core.extractors.bilibili_extractor.transcribe_local",
            return_value=(
                _long_text("B站本地转写"),
                [{"start": 0.0, "end": 1.0, "text": "B站本地转写"}],
            ),
        ),
    ):
        result = ext._try_audio_asr_fallback(
            "https://www.bilibili.com/video/BV1xx", "BV1xx", "B站基线视频", 180
        )

    assert result is not None
    assert result.success is True
    assert result.source == "bilibili_asr"
    assert result.language == "zh"
    assert result.metadata == {
        "bvid": "BV1xx",
        "api_provider": "faster_whisper",
        "model": "base",
    }
    assert result.segments == [{"start": 0.0, "end": 1.0, "text": "B站本地转写"}]


def test_bilibili_falls_back_to_dashscope_on_import_error(audio_file, tmp_path):
    ext = BilibiliExtractor()
    mp3_file = tmp_path / "audio.mp3"
    mp3_file.write_bytes(b"x" * 2048)
    with (
        mock.patch.object(BilibiliExtractor, "get_playurl_audio_urls", return_value=_bili_playurl()),
        mock.patch.object(BilibiliExtractor, "_download_audio", return_value=audio_file),
        mock.patch(
            "src.core.extractors.bilibili_extractor.transcribe_local",
            side_effect=ImportError("faster-whisper 未安装"),
        ),
        mock.patch.object(BilibiliExtractor, "_transcode_to_mp3", return_value=mp3_file),
        mock.patch.object(
            BilibiliExtractor,
            "_transcribe_via_dashscope",
            return_value=(
                _long_text("B站云端转写"),
                [{"start": 0.0, "end": 2.0, "text": "B站云端转写"}],
            ),
        ),
    ):
        result = ext._try_audio_asr_fallback(
            "https://www.bilibili.com/video/BV1xx", "BV1xx", "B站基线视频", 180
        )

    assert result is not None
    assert result.source == "bilibili_asr"
    assert result.metadata["api_provider"] == "dashscope_asr"
    assert result.metadata["model"] == "paraformer-v2"
    assert result.content == _long_text("B站云端转写")


def test_bilibili_returns_none_when_asr_fails(audio_file):
    ext = BilibiliExtractor()
    with (
        mock.patch.object(BilibiliExtractor, "get_playurl_audio_urls", return_value=_bili_playurl()),
        mock.patch.object(BilibiliExtractor, "_download_audio", return_value=audio_file),
        mock.patch(
            "src.core.extractors.bilibili_extractor.transcribe_local",
            side_effect=RuntimeError("model crashed"),
        ),
    ):
        result = ext._try_audio_asr_fallback(
            "https://www.bilibili.com/video/BV1xx", "BV1xx", "B站基线视频", 180
        )

    assert result is None


# ============================================================
# TikHub：本地 -> DashScope -> 阿里云 -> 占位
# ============================================================

def _tikhub_local_result(url: str) -> ExtractResult:
    return ExtractResult(
        success=True,
        platform="douyin",
        title="TikHub 基线视频",
        content=_long_text("TikHub 本地转写"),
        source="tikhub_asr",
        url=url,
        cost_tier=CostTier.PREMIUM,
        duration_seconds=60,
        language="zh",
        segments=[{"start": 0.0, "end": 1.0, "text": "TikHub 本地转写"}],
        metadata={"api_provider": "faster_whisper", "model": "base", "segments": 1},
    )


def test_tikhub_local_success(audio_file):
    ext = TikhubExtractor()
    url = "https://www.douyin.com/video/123"
    local_result = _tikhub_local_result(url)
    with (
        mock.patch.object(TikhubExtractor, "_download_audio", return_value=audio_file),
        mock.patch.object(TikhubExtractor, "_transcribe_local", return_value=local_result),
    ):
        result = ext._try_download_and_transcribe("https://cdn.example/video.mp4", url, "douyin", "标题", 60)

    assert result is local_result
    assert result.source == "tikhub_asr"
    assert result.metadata["api_provider"] == "faster_whisper"
    assert result.metadata["model"] == "base"


def test_tikhub_falls_back_to_dashscope(audio_file):
    ext = TikhubExtractor()
    url = "https://www.douyin.com/video/123"
    failed_local = ExtractResult(
        success=False,
        platform="douyin",
        title="标题",
        content="",
        source="tikhub_asr",
        url=url,
        cost_tier=CostTier.PREMIUM,
        error="Whisper ASR 返回了空转录",
    )
    dashscope_result = ExtractResult(
        success=True,
        platform="douyin",
        title="标题",
        content=_long_text("TikHub 云端转写"),
        source="tikhub_asr",
        url=url,
        cost_tier=CostTier.PREMIUM,
        duration_seconds=60,
        language="zh",
        segments=[{"start": 0.0, "end": 1.0, "text": "TikHub 云端转写"}],
        metadata={"api_provider": "dashscope_asr", "model": "paraformer-v2"},
    )
    with (
        mock.patch.object(TikhubExtractor, "_download_audio", return_value=audio_file),
        mock.patch.object(TikhubExtractor, "_transcribe_local", return_value=failed_local),
        mock.patch.object(TikhubExtractor, "_resolve_api_key", return_value="test-key"),
        mock.patch.object(TikhubExtractor, "_transcribe_with_dashscope", return_value=dashscope_result),
    ):
        result = ext._try_download_and_transcribe("https://cdn.example/video.mp4", url, "douyin", "标题", 60)

    assert result is dashscope_result
    assert result.source == "tikhub_asr"
    assert result.metadata["api_provider"] == "dashscope_asr"


def test_tikhub_returns_placeholder_when_all_asr_unavailable(audio_file):
    ext = TikhubExtractor()
    url = "https://www.douyin.com/video/123"
    failed_local = ExtractResult(
        success=False,
        platform="douyin",
        title="标题",
        content="",
        source="tikhub_asr",
        url=url,
        cost_tier=CostTier.PREMIUM,
        error="faster-whisper 未安装",
    )
    with (
        mock.patch.object(TikhubExtractor, "_download_audio", return_value=audio_file),
        mock.patch.object(TikhubExtractor, "_transcribe_local", return_value=failed_local),
        mock.patch.object(TikhubExtractor, "_resolve_api_key", return_value=None),
        mock.patch(
            "src.core.extractors.aliyun_asr_extractor.AliyunASRExtractor.is_available",
            return_value=False,
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
