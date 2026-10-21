"""共享 BilibiliClient 的 WBI、cookie 与 HTTP 封装测试。"""

from __future__ import annotations

import hashlib
import urllib.parse
from pathlib import Path
from unittest import mock

import httpx
import pytest

from src.core.platforms.bilibili_client import (
    BilibiliApiError,
    BilibiliClient,
    load_cookie_header,
)
from src.core.platforms.rate_limit import PlatformPolicy, PlatformRateLimiter


def test_mixin_key_is_deterministic_and_32_chars():
    orig = "".join(str(i % 10) for i in range(64))
    first = BilibiliClient.mixin_key(orig)
    second = BilibiliClient.mixin_key(orig)
    assert len(first) == 32
    assert first == second


def test_sign_adds_wts_and_w_rid():
    client = BilibiliClient()
    try:
        with mock.patch("src.core.platforms.bilibili_client.time.time", return_value=1_700_000_000):
            signed = client.sign({"mid": "123", "ps": "20"}, wbi_key="test-key")
    finally:
        client.close()

    params = {"mid": "123", "ps": "20", "wts": "1700000000"}
    query = urllib.parse.urlencode(sorted(params.items()))
    expected = hashlib.md5((query + "test-key").encode()).hexdigest()

    assert signed["wts"] == "1700000000"
    assert signed["w_rid"] == expected
    assert signed["mid"] == "123"
    assert signed["ps"] == "20"


def test_load_cookie_header_skips_expired_and_supports_http_only(tmp_path: Path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text(
        "\n".join(
            [
                "# Netscape HTTP Cookie File",
                ".bilibili.com\tTRUE\t/\tFALSE\t2000\tSESSDATA\tabc",
                ".bilibili.com\tTRUE\t/\tFALSE\t500\texpired\told",
                "#HttpOnly_.bilibili.com\tTRUE\t/\tFALSE\t0\tbuvid3\txyz",
                "malformed line",
            ]
        ),
        encoding="utf-8",
    )

    header = load_cookie_header(cookies, now=1000)

    assert header == "SESSDATA=abc; buvid3=xyz"


def test_load_cookie_header_filters_domain(tmp_path: Path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text(
        "\n".join(
            [
                ".bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\tabc",
                ".example.com\tTRUE\t/\tFALSE\t0\tsession\tsecret",
            ]
        ),
        encoding="utf-8",
    )

    header = load_cookie_header(cookies, now=1000, domain_suffix="bilibili.com")

    assert header == "SESSDATA=abc"


def test_cookie_header_is_sent_and_newlines_are_sanitized():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["cookie"] = request.headers.get("cookie", "")
        return httpx.Response(200, json={"code": 0})

    client = BilibiliClient(
        cookie_header="SESSDATA=abc\r\nX-Evil: 1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        client.get_json("/x/test")
    finally:
        client.close()

    assert seen["cookie"] == "SESSDATA=abc  X-Evil: 1"
    assert "\n" not in seen["cookie"]


def test_get_json_uses_base_url_and_returns_dict():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/x/test"
        return httpx.Response(200, json={"code": 0, "data": {"ok": True}})

    client = BilibiliClient(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    try:
        assert client.get_json("/x/test") == {"code": 0, "data": {"ok": True}}
    finally:
        client.close()


def test_get_json_rejects_non_object():
    client = BilibiliClient(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=[1, 2, 3])
            )
        )
    )
    try:
        with pytest.raises(BilibiliApiError):
            client.get_json("/x/test")
    finally:
        client.close()


def test_get_wbi_key_parses_nav_response():
    img_key = "7cd084941338484aae1ad9425b84077c"
    sub_key = "4932caff0ff746eab6f01bf08b70ac45"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/x/web-interface/nav"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": f"https://i0.hdslb.com/bfs/wbi/{img_key}.png",
                        "sub_url": f"https://i0.hdslb.com/bfs/wbi/{sub_key}.png",
                    }
                },
            },
        )

    client = BilibiliClient(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    try:
        assert client.get_wbi_key() == BilibiliClient.mixin_key(img_key + sub_key)
    finally:
        client.close()


def test_body_risk_code_notifies_limiter_and_opens_circuit():
    limiter = PlatformRateLimiter(
        {"bilibili": PlatformPolicy(circuit_threshold=2)}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": -352, "message": "风控校验失败"},
        )

    client = BilibiliClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        limiter=limiter,
    )
    try:
        with pytest.raises(BilibiliApiError) as exc_info:
            client.get_json("/x/space/wbi/arc/search")
        assert exc_info.value.error_code == "risk_control"
        assert limiter.circuit_state("bilibili") == "closed"

        with pytest.raises(BilibiliApiError):
            client.get_json("/x/space/wbi/arc/search")
        assert limiter.circuit_state("bilibili") == "open"

        with pytest.raises(BilibiliApiError) as exc_info:
            client.get_json("/x/space/wbi/arc/search")
        assert exc_info.value.error_code == "risk_control"
        assert "熔断" in str(exc_info.value)
    finally:
        client.close()
