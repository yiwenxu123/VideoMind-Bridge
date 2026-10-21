"""平台登录态解析、脱敏与健康检查测试。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx
import pytest

from src.core.platforms.session import (
    BilibiliSessionProvider,
    DouyinSessionProvider,
    SessionCheckUnsupported,
    SessionManager,
    XiaohongshuSessionProvider,
)

_ENV_NAMES = (
    "VMB_BILIBILI_COOKIE",
    "VMB_BILIBILI_SESSDATA",
    "VMB_BILIBILI_COOKIES_FILE",
    "VMB_XHS_COOKIE",
    "VMB_XHS_COOKIES_FILE",
    "VMB_COOKIES_FILE",
    "VMB_COOKIES_BROWSER",
    "DOUYIN_COOKIES_FILE",
)


@pytest.fixture(autouse=True)
def _clean_session_env(monkeypatch):
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def _cookie_file(tmp_path: Path) -> Path:
    future = int(time.time()) + 3600
    past = int(time.time()) - 3600
    path = tmp_path / "cookies.txt"
    path.write_text(
        "\n".join(
            [
                f".bilibili.com\tTRUE\t/\tTRUE\t{future}\tSESSDATA\tsecret-sess",
                f"#HttpOnly_.bilibili.com\tTRUE\t/\tTRUE\t{future}\tbili_jct\tsecret-jct",
                f"api.bilibili.com\tTRUE\t/\tTRUE\t{past}\texpired\told",
                f"example.com\tTRUE\t/\tTRUE\t{future}\tforeign\tleak",
                "# comment line",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _body(status: int, payload: dict, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        json=payload,
        headers=headers,
        request=httpx.Request("GET", "https://api.bilibili.com/x/web-interface/nav"),
    )


def _provider_for(response: httpx.Response) -> tuple[BilibiliSessionProvider, httpx.Client]:
    transport = httpx.MockTransport(lambda request: response)
    client = httpx.Client(transport=transport)
    return BilibiliSessionProvider(http_client=client), client


def test_raw_cookie_env_wins_over_sessdata_and_file(monkeypatch, tmp_path):
    monkeypatch.setenv("VMB_BILIBILI_COOKIE", "SESSDATA=raw; bili_jct=raw2")
    monkeypatch.setenv("VMB_BILIBILI_SESSDATA", "sessdata-value")
    monkeypatch.setenv("VMB_BILIBILI_COOKIES_FILE", str(_cookie_file(tmp_path)))
    provider = BilibiliSessionProvider()

    status = provider.status()

    assert status.configured is True
    assert status.source == "env"
    assert status.cookie_count == 2
    assert provider.headers() == {"Cookie": "SESSDATA=raw; bili_jct=raw2"}


def test_sessdata_env_builds_cookie_header(monkeypatch, tmp_path):
    monkeypatch.setenv("VMB_BILIBILI_SESSDATA", "only-sessdata")
    monkeypatch.setenv("VMB_BILIBILI_COOKIES_FILE", str(_cookie_file(tmp_path)))
    provider = BilibiliSessionProvider()

    assert provider.headers() == {"Cookie": "SESSDATA=only-sessdata"}
    assert provider.status().cookie_count == 1


def test_cookie_file_filters_foreign_domain_and_expired(monkeypatch, tmp_path):
    monkeypatch.setenv("VMB_BILIBILI_COOKIES_FILE", str(_cookie_file(tmp_path)))
    provider = BilibiliSessionProvider()

    status = provider.status()
    header = provider.headers()["Cookie"]

    assert status.source == "file"
    assert status.cookie_count == 2
    assert status.expires_at is not None
    assert "secret-sess" in header
    assert "secret-jct" in header
    assert "foreign" not in header
    assert "old" not in header


def test_missing_cookie_file_is_reported_without_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("VMB_BILIBILI_COOKIES_FILE", str(tmp_path / "missing.txt"))
    provider = BilibiliSessionProvider()

    status = provider.status()

    assert status.configured is False
    assert status.source == "file"
    assert status.warning == "no_valid_cookies"
    assert provider.headers() == {}


@pytest.mark.skipif(os.name != "posix", reason="POSIX 权限位")
def test_cookie_file_loose_permissions_produce_warning(monkeypatch, tmp_path):
    path = _cookie_file(tmp_path)
    path.chmod(0o644)
    monkeypatch.setenv("VMB_BILIBILI_COOKIES_FILE", str(path))
    provider = BilibiliSessionProvider()

    status = provider.status()

    assert status.configured is True
    assert status.warning == "cookie_file_permissions"


def test_status_never_contains_cookie_values(monkeypatch):
    monkeypatch.setenv("VMB_BILIBILI_COOKIE", "SESSDATA=super-secret; bili_jct=also-secret")
    provider = BilibiliSessionProvider()

    serialized = json.dumps(provider.status().to_dict(), ensure_ascii=False)

    assert "super-secret" not in serialized
    assert "also-secret" not in serialized
    assert provider.status().to_dict()["cookie_count"] == 2


def test_check_without_session_is_auth_required():
    provider = BilibiliSessionProvider()

    status = provider.check()

    assert status.valid is False
    assert status.error_code == "auth_required"
    assert status.last_checked is not None


@pytest.mark.parametrize(
    ("response", "valid", "error_code"),
    [
        (_body(200, {"code": 0, "data": {"isLogin": True}}), True, None),
        (_body(200, {"code": 0, "data": {"isLogin": False}}), False, "auth_required"),
        (_body(200, {"code": -101, "message": "未登录"}), False, "auth_required"),
        (_body(200, {"code": -352, "message": "风控校验失败"}), False, "risk_control"),
        (_body(401, {}), False, "auth_required"),
        (_body(412, {}), False, "risk_control"),
        (_body(500, {}), False, "upstream_error"),
    ],
)
def test_check_maps_upstream_results(monkeypatch, response, valid, error_code):
    monkeypatch.setenv("VMB_BILIBILI_COOKIE", "SESSDATA=x")
    provider, client = _provider_for(response)
    try:
        status = provider.check()
    finally:
        client.close()

    assert status.valid is valid
    assert status.error_code == error_code
    assert status.last_checked is not None


def test_session_manager_only_checks_supported_platforms():
    manager = SessionManager()

    with pytest.raises(SessionCheckUnsupported):
        manager.check("douyin")
    with pytest.raises(SessionCheckUnsupported):
        manager.check("xiaohongshu")
    with pytest.raises(SessionCheckUnsupported):
        manager.check("unknown-platform")


def test_session_manager_lists_all_platforms():
    manager = SessionManager()

    platforms = [status.platform for status in manager.statuses()]

    assert platforms == ["bilibili", "douyin", "ytdlp", "xiaohongshu", "youtube"]


def test_xhs_cookie_env_and_file_filter(monkeypatch, tmp_path):
    monkeypatch.setenv("VMB_XHS_COOKIE", "web_session=raw-secret")
    provider = XiaohongshuSessionProvider()

    assert provider.headers() == {"Cookie": "web_session=raw-secret"}
    assert provider.status().source == "env"

    monkeypatch.delenv("VMB_XHS_COOKIE")
    future = int(time.time()) + 3600
    past = int(time.time()) - 3600
    path = tmp_path / "xhs.txt"
    path.write_text(
        "\n".join(
            [
                f".xiaohongshu.com\tTRUE\t/\tTRUE\t{future}\tweb_session\tsecret-xhs",
                f".xiaohongshu.com\tTRUE\t/\tTRUE\t{past}\texpired\told",
                f"example.com\tTRUE\t/\tTRUE\t{future}\tforeign\tleak",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VMB_XHS_COOKIES_FILE", str(path))
    provider = XiaohongshuSessionProvider()
    status = provider.status()
    header = provider.headers()["Cookie"]

    assert status.source == "file"
    assert status.cookie_count == 1
    assert "secret-xhs" in header
    assert "foreign" not in header
    assert "secret-xhs" not in json.dumps(status.to_dict(), ensure_ascii=False)


def test_xhs_cookie_file_falls_back_to_generic_env(monkeypatch, tmp_path):
    future = int(time.time()) + 3600
    path = tmp_path / "generic.txt"
    path.write_text(
        f".xiaohongshu.com\tTRUE\t/\tTRUE\t{future}\tweb_session\tsecret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VMB_COOKIES_FILE", str(path))

    provider = XiaohongshuSessionProvider()

    assert provider.status().configured is True
    assert provider.status().source == "file"


def test_douyin_cookie_file_filters_foreign_domains(monkeypatch, tmp_path):
    future = int(time.time()) + 3600
    path = tmp_path / "douyin.txt"
    path.write_text(
        "\n".join(
            [
                f".douyin.com\tTRUE\t/\tTRUE\t{future}\tttwid\tsecret-douyin",
                f"example.com\tTRUE\t/\tTRUE\t{future}\tforeign\tleak",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DOUYIN_COOKIES_FILE", str(path))

    provider = DouyinSessionProvider()
    status = provider.status()
    header = provider.headers()["Cookie"]

    assert status.source == "file"
    assert status.cookie_count == 1
    assert "secret-douyin" in header
    assert "foreign" not in header
    assert "secret-douyin" not in json.dumps(status.to_dict(), ensure_ascii=False)
