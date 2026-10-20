"""ASR 降级链测试（阶段 1）：顺序、跳过、空文本、异常与全失败语义。"""

from __future__ import annotations

from unittest import mock

import pytest

from src.core.asr import (
    AsrChainError,
    AsrConfigError,
    AsrFailed,
    MediaRef,
    TranscribeOptions,
    Transcript,
    resolve_chain,
    transcribe_with_chain,
)


class _Backend:
    def __init__(self, name: str, text: str = "", available: bool = True, error: Exception | None = None):
        self.name = name
        self.text = text
        self.available = available
        self.error = error
        self.calls = 0

    def is_available(self) -> bool:
        return self.available

    def transcribe(self, media: MediaRef, options: TranscribeOptions) -> Transcript:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return Transcript(text=self.text, provider=self.name)


def _patch_backends(*backends: _Backend):
    mapping = {b.name: b for b in backends}

    def factory(name, config=None):
        if name not in mapping:
            raise AsrConfigError(f"未知 ASR 后端: {name}")
        return mapping[name]

    return mock.patch("src.core.asr.chain.create_transcriber", side_effect=factory)


def _media(tmp_path):
    path = tmp_path / "a.wav"
    path.write_bytes(b"x")
    return MediaRef(path=path)


def test_returns_first_non_empty_and_records_attempts(tmp_path):
    first = _Backend("first", text="")
    second = _Backend("second", text="结果")
    with _patch_backends(first, second):
        transcript = transcribe_with_chain(_media(tmp_path), chain=["first", "second"])

    assert transcript.text == "结果"
    assert transcript.provider == "second"
    assert transcript.metadata["attempts"][0]["provider"] == "first"
    assert transcript.metadata["attempts"][0]["status"] == "empty"
    assert first.calls == 1
    assert second.calls == 1


def test_skips_unavailable_backend_without_calling(tmp_path):
    unavailable = _Backend("unavailable", available=False)
    backup = _Backend("backup", text="ok")
    with _patch_backends(unavailable, backup):
        transcript = transcribe_with_chain(_media(tmp_path), chain=["unavailable", "backup"])

    assert transcript.text == "ok"
    assert unavailable.calls == 0
    assert transcript.metadata["attempts"][0]["status"] == "unavailable"


def test_falls_through_on_exception(tmp_path):
    failing = _Backend("failing", error=AsrFailed("网络挂了"))
    backup = _Backend("backup", text="ok")
    with _patch_backends(failing, backup):
        transcript = transcribe_with_chain(_media(tmp_path), chain=["failing", "backup"])

    assert transcript.text == "ok"
    attempt = transcript.metadata["attempts"][0]
    assert attempt["provider"] == "failing"
    assert attempt["status"] == "asr_failed"
    assert "网络挂了" in attempt["message"]


def test_all_fail_raises_chain_error_with_attempts(tmp_path):
    with _patch_backends(_Backend("a", available=False), _Backend("b", error=AsrFailed("boom"))):
        with pytest.raises(AsrChainError) as exc:
            transcribe_with_chain(_media(tmp_path), chain=["a", "b"])

    statuses = [attempt["status"] for attempt in exc.value.attempts]
    assert statuses == ["unavailable", "asr_failed"]


def test_unknown_backend_recorded_as_config_error(tmp_path):
    with _patch_backends(_Backend("known", text="ok")):
        transcript = transcribe_with_chain(_media(tmp_path), chain=["ghost", "known"])

    assert transcript.text == "ok"
    assert transcript.metadata["attempts"][0]["status"] == "config_error"


def test_empty_chain_raises(tmp_path):
    with pytest.raises(AsrChainError):
        transcribe_with_chain(_media(tmp_path), chain=[])


def test_resolve_chain_precedence(monkeypatch):
    monkeypatch.setenv("VMB_ASR_CHAIN", "sensevoice, faster_whisper")
    assert resolve_chain() == ["sensevoice", "faster_whisper"]
    assert resolve_chain(["aliyun"]) == ["aliyun"]

    monkeypatch.delenv("VMB_ASR_CHAIN")
    assert resolve_chain() == ["faster_whisper", "dashscope"]
