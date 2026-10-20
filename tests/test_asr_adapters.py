"""ASR 适配器测试（阶段 1）：四个后端的可用性、映射与错误语义。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.core.asr import AsrEmpty, AsrFailed, AsrUnavailable, MediaRef, TranscribeOptions
from src.core.asr.adapters import aliyun as aliyun_mod
from src.core.asr.adapters import dashscope as dashscope_mod
from src.core.asr.adapters import faster_whisper as fw_mod
from src.core.asr.adapters import sensevoice as sv_mod


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    path = tmp_path / "audio.m4s"
    path.write_bytes(b"x" * 2048)
    return path


# ============================================================
# faster_whisper
# ============================================================

def test_faster_whisper_capabilities_uses_env_model(monkeypatch):
    monkeypatch.setenv("VMB_WHISPER_MODEL", "small")
    monkeypatch.setattr(fw_mod, "_whisper_importable", lambda: True)
    caps = fw_mod.FasterWhisperTranscriber().capabilities()
    assert caps.available is True
    assert caps.model == "small"
    assert caps.timestamps is True


def test_faster_whisper_maps_segments(monkeypatch, audio):
    monkeypatch.delenv("VMB_WHISPER_MODEL", raising=False)
    monkeypatch.setattr(fw_mod, "_whisper_importable", lambda: True)
    monkeypatch.setattr(
        fw_mod, "run_whisper",
        lambda path, language, model_size: ("你好", [{"start": 0, "end": 1.5, "text": "你好"}]),
    )
    transcript = fw_mod.FasterWhisperTranscriber().transcribe(
        MediaRef(path=audio), TranscribeOptions(language="zh")
    )
    assert transcript.text == "你好"
    assert transcript.provider == "faster-whisper"
    assert transcript.model == "base"
    assert transcript.segments[0].to_dict() == {"start": 0.0, "end": 1.5, "text": "你好"}


def test_faster_whisper_empty_result_raises(monkeypatch, audio):
    monkeypatch.setattr(fw_mod, "_whisper_importable", lambda: True)
    monkeypatch.setattr(fw_mod, "run_whisper", lambda path, language, model_size: ("", None))
    with pytest.raises(AsrEmpty):
        fw_mod.FasterWhisperTranscriber().transcribe(MediaRef(path=audio), TranscribeOptions())


def test_faster_whisper_unavailable_without_dependency(monkeypatch, audio):
    monkeypatch.setattr(fw_mod, "_whisper_importable", lambda: False)
    with pytest.raises(AsrUnavailable):
        fw_mod.FasterWhisperTranscriber().transcribe(MediaRef(path=audio), TranscribeOptions())


# ============================================================
# dashscope
# ============================================================

def test_dashscope_unavailable_without_key(monkeypatch, audio):
    monkeypatch.setattr(dashscope_mod, "resolve_extractor_key", lambda name: None)
    backend = dashscope_mod.DashScopeTranscriber()
    assert backend.capabilities().available is False
    with pytest.raises(AsrUnavailable):
        backend.transcribe(MediaRef(path=audio), TranscribeOptions())


def test_dashscope_maps_result(monkeypatch, tmp_path):
    mp3 = tmp_path / "audio.mp3"
    mp3.write_bytes(b"x" * 2048)
    monkeypatch.setattr(dashscope_mod, "resolve_extractor_key", lambda name: "test-key")
    monkeypatch.setattr(
        dashscope_mod, "_transcribe_audio_data",
        lambda path, key: ("云端结果", [{"start": 0.0, "end": 1.0, "text": "云端结果"}]),
    )
    transcript = dashscope_mod.DashScopeTranscriber().transcribe(
        MediaRef(path=mp3), TranscribeOptions(language="zh")
    )
    assert transcript.text == "云端结果"
    assert transcript.provider == "dashscope"
    assert transcript.model == "paraformer-v2"
    assert transcript.segments[0].text == "云端结果"


def test_dashscope_prepare_audio_passthrough_for_non_m4s(tmp_path):
    path = tmp_path / "audio.mp3"
    path.write_bytes(b"x")
    prepared, cleanup = dashscope_mod._prepare_audio(path)
    assert prepared == path
    assert cleanup is None


# ============================================================
# aliyun
# ============================================================

def test_aliyun_requires_three_keys(monkeypatch):
    values = {"aliyun_access_key_id": "a", "aliyun_access_key_secret": "", "aliyun_appkey": "c"}
    monkeypatch.setattr(aliyun_mod, "resolve_extractor_key", lambda name: values.get(name))
    assert aliyun_mod.AliyunTranscriber().capabilities().available is False


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "status": 0,
            "result": {"language": "zh", "sentences": [
                {"begin_time": 0, "end_time": 1000, "text": "你好"},
            ]},
        }


class _FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False

    def post(self, *args, **kwargs) -> _FakeResponse:
        return _FakeResponse()


def test_aliyun_transcribe_parses_sentences(monkeypatch, audio):
    monkeypatch.setattr(aliyun_mod, "resolve_extractor_key", lambda name: "test-key")
    monkeypatch.setattr(aliyun_mod.httpx, "Client", _FakeClient)
    transcript = aliyun_mod.AliyunTranscriber().transcribe(
        MediaRef(path=audio), TranscribeOptions()
    )
    assert transcript.text == "你好"
    assert transcript.provider == "aliyun"
    assert transcript.segments[0].start == 0.0
    assert transcript.segments[0].end == 1.0


# ============================================================
# sensevoice
# ============================================================

def test_sensevoice_unavailable_when_script_missing(monkeypatch):
    monkeypatch.setattr(sv_mod, "_resolve_script", lambda: Path("/nonexistent/sensevoice.py"))
    caps = sv_mod.SenseVoiceTranscriber().capabilities()
    assert caps.available is False
    assert "脚本缺失" in caps.notes


def test_sensevoice_parses_last_json_line(monkeypatch, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x" * 2048)

    class _Proc:
        returncode = 0
        stdout = '[sensevoice] done\n{"text": "识别结果"}\n'
        stderr = ""

    monkeypatch.setattr(sv_mod, "_resolve_script", lambda: wav)
    monkeypatch.setattr(sv_mod, "_resolve_python", lambda: sys.executable)
    monkeypatch.setattr(sv_mod, "_model_ready", lambda model_dir: True)
    monkeypatch.setattr(sv_mod.subprocess, "run", lambda *args, **kwargs: _Proc())

    transcript = sv_mod.SenseVoiceTranscriber().transcribe(
        MediaRef(path=wav), TranscribeOptions()
    )
    assert transcript.text == "识别结果"
    assert transcript.provider == "sensevoice"
    assert transcript.segments is None


def test_sensevoice_non_json_output_raises(monkeypatch, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x" * 2048)

    class _Proc:
        returncode = 0
        stdout = "not a json line\n"
        stderr = ""

    monkeypatch.setattr(sv_mod, "_resolve_script", lambda: wav)
    monkeypatch.setattr(sv_mod, "_resolve_python", lambda: sys.executable)
    monkeypatch.setattr(sv_mod, "_model_ready", lambda model_dir: True)
    monkeypatch.setattr(sv_mod.subprocess, "run", lambda *args, **kwargs: _Proc())

    with pytest.raises(AsrFailed):
        sv_mod.SenseVoiceTranscriber().transcribe(MediaRef(path=wav), TranscribeOptions())


def test_sensevoice_nonzero_exit_raises(monkeypatch, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x" * 2048)

    class _Proc:
        returncode = 1
        stdout = ""
        stderr = "[sensevoice] model files missing\n"

    monkeypatch.setattr(sv_mod, "_resolve_script", lambda: wav)
    monkeypatch.setattr(sv_mod, "_resolve_python", lambda: sys.executable)
    monkeypatch.setattr(sv_mod, "_model_ready", lambda model_dir: True)
    monkeypatch.setattr(sv_mod.subprocess, "run", lambda *args, **kwargs: _Proc())

    with pytest.raises(AsrFailed) as exc:
        sv_mod.SenseVoiceTranscriber().transcribe(MediaRef(path=wav), TranscribeOptions())
    assert "model files missing" in str(exc.value)
