"""ASR 注册表测试（阶段 1）：注册不实例化、未知后端报错、配置透传。"""

from __future__ import annotations

import pytest

from src.core.asr import (
    AsrConfigError,
    Capabilities,
    MediaRef,
    TranscribeOptions,
    Transcript,
    create_transcriber,
    get_transcriber_class,
    list_transcriber_names,
    register_transcriber,
)
from src.core.asr.base import Transcriber


class _FakeTranscriber(Transcriber):
    name = "fake_registry_backend"
    constructed = 0

    def __init__(self, config=None):
        super().__init__(config)
        type(self).constructed += 1

    def capabilities(self) -> Capabilities:
        return Capabilities(name=self.name, available=True)

    def transcribe(self, media: MediaRef, options: TranscribeOptions) -> Transcript:
        return Transcript(text="ok", provider=self.name)


def test_register_does_not_instantiate_and_create_does():
    _FakeTranscriber.constructed = 0
    register_transcriber(_FakeTranscriber.name, _FakeTranscriber)

    assert _FakeTranscriber.name in list_transcriber_names()
    assert _FakeTranscriber.constructed == 0

    backend = create_transcriber(_FakeTranscriber.name)
    assert isinstance(backend, _FakeTranscriber)
    assert _FakeTranscriber.constructed == 1


def test_unknown_backend_raises_config_error_with_available_list():
    with pytest.raises(AsrConfigError) as exc:
        get_transcriber_class("no_such_backend")
    message = str(exc.value)
    assert "no_such_backend" in message
    assert "faster_whisper" in message


def test_create_passes_config_through():
    register_transcriber("fake_with_config", _FakeTranscriber)
    backend = create_transcriber("fake_with_config", {"model": "tiny"})
    assert backend.config == {"model": "tiny"}
