"""`src.cli._run_local_asr` 的行为测试（A2 后唯一从 v1 存活下来的路径）。

这条路径 = 本地文件 → ffmpeg 转 16k wav → ASR 降级链，没有下载、没有 AI 摘要。
函数体内的 import 意味着 patch 模块属性即可生效（不需要改实现）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import src.core.asr as asr_pkg  # noqa: E402
import src.core.media as media_pkg  # noqa: E402
from src.cli import _run_local_asr  # noqa: E402


def _args(url: str, *, json_output: bool = True, asr: str | None = None,
          asr_chain: str | None = None, asr_language: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        url=url, json_output=json_output, asr=asr, asr_chain=asr_chain,
        asr_language=asr_language,
    )


def _transcript(text: str = "你好世界", provider: str = "sensevoice"):
    return asr_pkg.Transcript(
        text=text,
        provider=provider,
        model="sensevoice-small",
        model_version="2024-07",
        language="zh",
        duration_seconds=1.5,
        segments=[{"start": 0.0, "end": 1.5, "text": text}],
    )


@pytest.fixture
def media_file(tmp_path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"x")
    return media


@pytest.fixture
def patched(monkeypatch, tmp_path):
    """拦掉 ffmpeg 与 ASR 链，记录传进来的 chain。"""
    calls: list[dict] = []

    def fake_wav(src, dest, **kwargs):
        dest = Path(dest)
        dest.write_bytes(b"RIFF")
        return dest

    def fake_transcribe(media, options=None, chain=None, **kwargs):
        calls.append({"media": media, "options": options, "chain": chain})
        return _transcript()

    monkeypatch.setattr(media_pkg, "to_16k_mono_wav", fake_wav)
    monkeypatch.setattr(asr_pkg, "transcribe_with_chain", fake_transcribe)
    return calls


def test_success_prints_contract_shaped_json(media_file, patched, capsys):
    code = _run_local_asr(_args(str(media_file)))

    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is True
    assert data["platform"] == "local"
    assert data["source"] == "local_asr"
    assert data["method"] == "asr"
    assert data["completeness"] == "full"
    assert data["content"] == "你好世界"
    assert data["asr"] == {
        "provider": "sensevoice",
        "model": "sensevoice-small",
        "model_version": "2024-07",
    }
    assert len(patched) == 1, "只应调用一次 ASR 链"


def test_empty_transcript_is_failure(media_file, patched, capsys, monkeypatch):
    monkeypatch.setattr(asr_pkg, "transcribe_with_chain", lambda *a, **k: _transcript("   "))

    code = _run_local_asr(_args(str(media_file)))

    assert code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is False
    assert data["completeness"] == "none"


def test_missing_file_returns_2(tmp_path, capsys):
    code = _run_local_asr(_args(str(tmp_path / "nope.mp4")))

    assert code == 2
    assert "文件不存在" in capsys.readouterr().err


def test_asr_chain_precedence(media_file, patched):
    _run_local_asr(_args(str(media_file), asr_chain="a, b"))
    _run_local_asr(_args(str(media_file), asr="dashscope"))
    _run_local_asr(_args(str(media_file)))

    assert patched[0]["chain"] == ["a", "b"]
    assert patched[1]["chain"] == ["dashscope"]
    assert patched[2]["chain"] is None


def test_transcription_error_returns_1(media_file, patched, capsys, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("backend down")

    monkeypatch.setattr(asr_pkg, "transcribe_with_chain", boom)

    code = _run_local_asr(_args(str(media_file)))

    assert code == 1
    assert "转写失败" in capsys.readouterr().err
