"""两个回归脚本的 token 读取必须一致（2026-11-24 统一为 VIDEOMIND_API_TOKEN）。

背景：脚本原先读 VMB_API_TOKEN，而服务端只认 VIDEOMIND_API_TOKEN（src/api/auth.py），
于是「设了 token 仍然匿名」这件事没有任何报错。这里把两个脚本的解析行为锁在一起，
避免以后又各改一套。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(module_name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(
    params=[
        ("discovery", "check_discovery_links.py"),
        ("real", "check_real_links.py"),
    ],
    ids=["discovery_links", "real_links"],
)
def script(request) -> ModuleType:
    name, filename = request.param
    return _load(f"_vmb_token_{name}", filename)


def test_canonical_env_wins(script, monkeypatch):
    monkeypatch.delenv("VMB_API_TOKEN", raising=False)
    monkeypatch.setenv("VIDEOMIND_API_TOKEN", "  canonical-token  ")
    assert script.resolve_api_token() == "canonical-token"


def test_legacy_env_still_works_with_deprecation_warning(script, monkeypatch, capsys):
    monkeypatch.delenv("VIDEOMIND_API_TOKEN", raising=False)
    monkeypatch.setenv("VMB_API_TOKEN", "legacy-token")

    assert script.resolve_api_token() == "legacy-token"
    err = capsys.readouterr().err
    assert "deprecated" in err
    assert "VIDEOMIND_API_TOKEN" in err


def test_canonical_takes_priority_over_legacy(script, monkeypatch, capsys):
    monkeypatch.setenv("VIDEOMIND_API_TOKEN", "canonical")
    monkeypatch.setenv("VMB_API_TOKEN", "legacy")

    assert script.resolve_api_token() == "canonical"
    assert "deprecated" not in capsys.readouterr().err


def test_no_token_returns_empty(script, monkeypatch):
    monkeypatch.delenv("VIDEOMIND_API_TOKEN", raising=False)
    monkeypatch.delenv("VMB_API_TOKEN", raising=False)
    assert script.resolve_api_token() == ""


def test_both_scripts_agree_on_env_names():
    discovery = _load("_vmb_token_names_discovery", "check_discovery_links.py")
    real = _load("_vmb_token_names_real", "check_real_links.py")
    assert discovery.CANONICAL_TOKEN_ENV == real.CANONICAL_TOKEN_ENV == "VIDEOMIND_API_TOKEN"
    assert discovery.LEGACY_TOKEN_ENV == real.LEGACY_TOKEN_ENV == "VMB_API_TOKEN"
