"""douyin-api 网关契约自检脚本的测试（不联网）。"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.check_douyin_gateway_contract import EXPECTED_VERSION, PATH, main  # noqa: E402


def _spec(version: str = EXPECTED_VERSION, with_path: bool = True, with_param: bool = True) -> dict:
    paths: dict = {}
    if with_path:
        params = [{"name": "aweme_id", "in": "query"}] if with_param else [{"name": "id", "in": "query"}]
        paths[PATH] = {"get": {"parameters": params}}
    return {"info": {"version": version, "title": "Douyin TikTok Download API"}, "paths": paths}


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _patch(monkeypatch, payload: dict) -> None:
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(payload))


def test_contract_ok(monkeypatch, capsys):
    _patch(monkeypatch, _spec())
    monkeypatch.setattr(sys, "argv", ["check"])
    assert main() == 0
    assert "契约成立" in capsys.readouterr().out


def test_missing_path_fails(monkeypatch, capsys):
    _patch(monkeypatch, _spec(with_path=False))
    monkeypatch.setattr(sys, "argv", ["check"])
    assert main() == 1
    assert "路径不见了" in capsys.readouterr().err


def test_missing_param_fails(monkeypatch, capsys):
    _patch(monkeypatch, _spec(with_param=False))
    monkeypatch.setattr(sys, "argv", ["check"])
    assert main() == 1
    assert "参数不见了" in capsys.readouterr().err


def test_unreachable_returns_2(monkeypatch, capsys):
    def _boom(*a, **k):
        raise httpx.ConnectError("refused", request=httpx.Request("GET", "http://x"))

    monkeypatch.setattr(httpx, "get", _boom)
    monkeypatch.setattr(sys, "argv", ["check"])
    assert main() == 2
    assert "pm2" in capsys.readouterr().err, "要给出可执行动作"


def test_version_change_is_reported_not_failed(monkeypatch, capsys):
    _patch(monkeypatch, _spec(version="V9.9.9"))
    monkeypatch.setattr(sys, "argv", ["check", "--json"])
    assert main() == 0
    out = capsys.readouterr().out
    assert '"version_changed": true' in out
