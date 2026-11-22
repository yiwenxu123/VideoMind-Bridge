"""yt-dlp 可执行文件解析优先级测试（2026-11-22）。

背景：`pyproject.toml` 声明 `yt-dlp>=2026.7.4`、venv 也装了 `2026.07.04`，
但代码把 PATH 排在最前，实际执行的是 Homebrew 的 `2026.03.13`（旧 4 个月）。
抖音最吃版本，这类"声明一套、跑另一套"的漂移必须被测试锁住。

契约（顺序固定）：VMB_YTDLP_BIN > 项目 venv > PATH > ~/.local/bin
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.utils import ytdlp_bin


def _fake_bin(tmp_path: Path) -> Path:
    path = tmp_path / "yt-dlp"
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_env_override_wins(monkeypatch, tmp_path):
    """显式覆盖是最高优先级——给非常规部署留的逃生口。"""
    monkeypatch.setenv("VMB_YTDLP_BIN", "/custom/path/yt-dlp")
    assert ytdlp_bin.resolve_ytdlp() == "/custom/path/yt-dlp"


def test_venv_preferred_over_path(monkeypatch, tmp_path):
    """venv 里存在时，必须优先于 PATH 里的全局安装。"""
    venv_bin = _fake_bin(tmp_path)
    monkeypatch.delenv("VMB_YTDLP_BIN", raising=False)
    monkeypatch.setattr(ytdlp_bin, "_venv_candidates", lambda: [venv_bin])
    monkeypatch.setattr(ytdlp_bin.shutil, "which", lambda name: "/usr/local/bin/yt-dlp")

    assert ytdlp_bin.resolve_ytdlp() == str(venv_bin)


def test_falls_back_to_path_when_venv_missing(monkeypatch, tmp_path):
    """venv 没有时退回 PATH，不能直接判定"未安装"。"""
    monkeypatch.delenv("VMB_YTDLP_BIN", raising=False)
    monkeypatch.setattr(ytdlp_bin, "_venv_candidates", lambda: [tmp_path / "nope"])
    monkeypatch.setattr(ytdlp_bin.shutil, "which", lambda name: "/usr/local/bin/yt-dlp")

    assert ytdlp_bin.resolve_ytdlp() == "/usr/local/bin/yt-dlp"


def test_returns_none_when_nothing_found(monkeypatch, tmp_path):
    monkeypatch.delenv("VMB_YTDLP_BIN", raising=False)
    monkeypatch.setattr(ytdlp_bin, "_venv_candidates", lambda: [tmp_path / "nope"])
    monkeypatch.setattr(ytdlp_bin.shutil, "which", lambda name: None)
    monkeypatch.setattr(ytdlp_bin.Path, "home", lambda: tmp_path / "home")

    assert ytdlp_bin.resolve_ytdlp() is None
    # 命令构造不能返回 None——退回字面量，让调用方报"未安装"
    assert ytdlp_bin.ytdlp_command() == "yt-dlp"


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / ".venv").exists(),
    reason="本机没有项目 venv，跳过真实解析校验",
)
def test_real_project_prefers_venv_binary(monkeypatch):
    """真实环境校验：本项目里解析结果应落在自己的 .venv 下。"""
    monkeypatch.delenv("VMB_YTDLP_BIN", raising=False)
    resolved = ytdlp_bin.resolve_ytdlp()
    assert resolved is not None
    assert ".venv" in resolved, f"解析到了项目外的 yt-dlp: {resolved}"
