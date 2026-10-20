"""ASR 统一类型测试（阶段 1）"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.asr import (
    AsrInputError,
    Capabilities,
    MediaRef,
    Segment,
    TranscribeOptions,
    Transcript,
)
from src.core.models import CostTier


def test_segment_to_dict_omits_empty_speaker():
    assert Segment(start=0.0, end=1.0, text="你好").to_dict() == {
        "start": 0.0,
        "end": 1.0,
        "text": "你好",
    }
    assert Segment(start=0.0, end=1.0, text="你好", speaker="S1").to_dict()["speaker"] == "S1"


def test_transcript_to_dict_roundtrip_fields():
    transcript = Transcript(
        text="内容",
        provider="faster-whisper",
        model="base",
        model_version="1.2.1",
        language="zh",
        segments=[Segment(start=0.0, end=1.0, text="内容")],
        cost_tier=CostTier.CHEAP,
        metadata={"attempts": []},
    )
    data = transcript.to_dict()
    assert data["text"] == "内容"
    assert data["provider"] == "faster-whisper"
    assert data["model_version"] == "1.2.1"
    assert data["segments"] == [{"start": 0.0, "end": 1.0, "text": "内容"}]
    assert data["cost_tier"] == "cheap"


def test_transcript_to_dict_omits_optional_empty_fields():
    data = Transcript(text="x").to_dict()
    assert "model_version" not in data
    assert "segments" not in data
    assert "metadata" not in data


def test_media_ref_require_path_raises_without_path():
    with pytest.raises(AsrInputError):
        MediaRef(url="https://example.com/a.mp3").require_path()
    assert MediaRef(path=Path("/tmp/a.wav")).require_path() == Path("/tmp/a.wav")


def test_capabilities_to_dict_includes_notes_when_present():
    caps = Capabilities(name="sensevoice", available=False, notes="未找到脚本")
    data = caps.to_dict()
    assert data["available"] is False
    assert data["notes"] == "未找到脚本"
    assert data["cost_tier"] == "cheap"


def test_transcribe_options_defaults():
    options = TranscribeOptions()
    assert options.language is None
    assert options.timestamps is True
    assert options.extra == {}
