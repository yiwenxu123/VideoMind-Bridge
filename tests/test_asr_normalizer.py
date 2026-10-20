"""Transcript → ExtractResult 映射测试（阶段 1）。"""

from __future__ import annotations

from src.core.asr import Segment, Transcript, transcript_to_extract_result
from src.core.models import CostTier


def test_maps_new_and_legacy_metadata_keys():
    transcript = Transcript(
        text="hello",
        provider="faster-whisper",
        model="base",
        model_version="1.2.1",
        language="zh",
        segments=[Segment(start=0.0, end=1.0, text="hello")],
        metadata={"attempts": [{"provider": "x", "status": "empty"}], "elapsed_seconds": 1.25},
    )
    result = transcript_to_extract_result(
        transcript,
        url="https://example.com/v",
        platform="bilibili",
        title="标题",
        source="bilibili_asr",
        cost_tier=CostTier.FREE,
        metadata={"bvid": "BV1"},
    )

    assert result.success is True
    assert result.content == "hello"
    assert result.language == "zh"
    assert result.segments == [{"start": 0.0, "end": 1.0, "text": "hello"}]
    assert result.metadata["asr_provider"] == "faster-whisper"
    assert result.metadata["asr_model"] == "base"
    assert result.metadata["asr_model_version"] == "1.2.1"
    assert result.metadata["api_provider"] == "faster_whisper"
    assert result.metadata["model"] == "base"
    assert result.metadata["asr_attempts"][0]["status"] == "empty"
    assert result.metadata["asr_elapsed_seconds"] == 1.25
    assert result.metadata["bvid"] == "BV1"


def test_maps_dashscope_and_aliyun_legacy_provider_names():
    for provider, legacy in (("dashscope", "dashscope_asr"), ("aliyun", "aliyun_asr")):
        result = transcript_to_extract_result(
            Transcript(text="x", provider=provider, model="m"),
            url="u", platform="p", title="t", source="s", cost_tier=CostTier.CHEAP,
        )
        assert result.metadata["api_provider"] == legacy


def test_unknown_provider_keeps_name_and_no_segments():
    result = transcript_to_extract_result(
        Transcript(text="x", provider="custom", model="m"),
        url="u", platform="p", title="t", source="s", cost_tier=CostTier.CHEAP,
    )
    assert result.metadata["api_provider"] == "custom"
    assert result.segments is None


def test_duration_falls_back_to_transcript_value():
    transcript = Transcript(text="x", duration_seconds=42.0)
    result = transcript_to_extract_result(
        transcript, url="u", platform="p", title="t", source="s", cost_tier=CostTier.CHEAP,
    )
    assert result.duration_seconds == 42.0

    result_explicit = transcript_to_extract_result(
        transcript, url="u", platform="p", title="t", source="s",
        cost_tier=CostTier.CHEAP, duration_seconds=10.0,
    )
    assert result_explicit.duration_seconds == 10.0
