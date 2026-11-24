"""ASR 适配器测试（阶段 1）：四个后端的可用性、映射与错误语义。"""

from __future__ import annotations

import subprocess
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


def test_dashscope_requires_public_url(monkeypatch):
    monkeypatch.setattr(dashscope_mod, "resolve_extractor_key", lambda name: "test-key")
    monkeypatch.delenv("VMB_MEDIA_DIR", raising=False)
    monkeypatch.delenv("VMB_PUBLIC_URL", raising=False)
    backend = dashscope_mod.DashScopeTranscriber()
    assert backend.capabilities().available is False

    monkeypatch.setenv("VMB_MEDIA_DIR", "/tmp/media")
    monkeypatch.setenv("VMB_PUBLIC_URL", "https://example.com")
    assert backend.capabilities().available is True


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


def test_sensevoice_default_script_is_packaged():
    """脚本必须位于 src 包内，wheel 安装后仍可被适配器找到。"""
    assert sv_mod.DEFAULT_SCRIPT.is_file()
    assert "src/core/asr/scripts" in str(sv_mod.DEFAULT_SCRIPT)


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


# ---- 2026-11-24：capabilities 真探测解释器依赖（只存在文件不代表能跑）----


def _fake_python_and_model(monkeypatch, tmp_path):
    """把三重检查都搭成「文件齐全」，让 tests 只关心探测这一步。"""
    script = tmp_path / "sensevoice_transcribe.py"
    script.write_text("", encoding="utf-8")
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    monkeypatch.setattr(sv_mod, "_resolve_script", lambda: script)
    monkeypatch.setattr(sv_mod, "_resolve_python", lambda: sys.executable)
    monkeypatch.setattr(sv_mod, "_resolve_model_dir", lambda: model_dir)
    monkeypatch.setattr(sv_mod, "_model_ready", lambda _dir: True)
    monkeypatch.setattr(sv_mod, "_RUNTIME_PROBE_CACHE", {})


def test_sensevoice_capabilities_unavailable_when_probe_fails(monkeypatch, tmp_path):
    """文件齐全但解释器没装 sherpa-onnx 时必须报不可用，并把原因写进 notes。"""
    _fake_python_and_model(monkeypatch, tmp_path)
    monkeypatch.setattr(
        sv_mod,
        "_probe_runtime",
        lambda python: (False, "ModuleNotFoundError: No module named 'sherpa_onnx'"),
    )

    caps = sv_mod.SenseVoiceTranscriber().capabilities()

    assert caps.available is False
    assert "sherpa-onnx" in caps.notes


def test_sensevoice_capabilities_available_when_probe_passes(monkeypatch, tmp_path):
    _fake_python_and_model(monkeypatch, tmp_path)
    monkeypatch.setattr(sv_mod, "_probe_runtime", lambda python: (True, ""))

    caps = sv_mod.SenseVoiceTranscriber().capabilities()

    assert caps.available is True
    assert "已确认" in caps.notes


def test_probe_runtime_caches_per_interpreter(monkeypatch):
    """capabilities 会被 /api/v1/capabilities 反复调用，子进程只能起一次。"""
    calls: list[list[str]] = []

    class _Ok:
        returncode = 0
        stdout = ""
        stderr = ""

    def _run(args, **kwargs):
        calls.append(list(args))
        return _Ok()

    monkeypatch.setattr(sv_mod, "_RUNTIME_PROBE_CACHE", {})
    monkeypatch.setattr(sv_mod.subprocess, "run", _run)

    assert sv_mod._probe_runtime("/fake/python") == (True, "")
    assert sv_mod._probe_runtime("/fake/python") == (True, "")
    assert len(calls) == 1
    assert calls[0][1:] == ["-c", "import sherpa_onnx, soundfile"]


def test_probe_runtime_reports_import_error_detail(monkeypatch):
    class _Bad:
        returncode = 1
        stdout = ""
        stderr = "Traceback (most recent call last):\nModuleNotFoundError: No module named 'soundfile'\n"

    monkeypatch.setattr(sv_mod, "_RUNTIME_PROBE_CACHE", {})
    monkeypatch.setattr(sv_mod.subprocess, "run", lambda *a, **k: _Bad())

    ok, detail = sv_mod._probe_runtime("/fake/python")

    assert ok is False
    assert "soundfile" in detail


def test_probe_runtime_survives_timeout(monkeypatch):
    """探测超时不能被当成「可用」，也不能把异常抛给 /capabilities。"""

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="python", timeout=1)

    monkeypatch.setattr(sv_mod, "_RUNTIME_PROBE_CACHE", {})
    monkeypatch.setattr(sv_mod.subprocess, "run", _timeout)

    ok, detail = sv_mod._probe_runtime("/fake/python")

    assert ok is False
    assert detail
