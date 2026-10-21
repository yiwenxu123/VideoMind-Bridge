"""yt-dlp 子进程网络参数、cookies 与熔断跳过测试。"""

from __future__ import annotations

import subprocess
from typing import Any

from src.core.extractors.ytdlp_asr_extractor import YtDlpASRExtractor
from src.core.extractors.ytdlp_extractor import YtDlpExtractor
from src.core.media.ytdlp_fetcher import YtDlpMediaFetcher
from src.core.platforms.ytdlp_options import ytdlp_cookie_args, ytdlp_network_args


def _clear_ytdlp_env(monkeypatch) -> None:
    for name in (
        "VMB_YTDLP_SLEEP_REQUESTS",
        "VMB_YTDLP_RETRIES",
        "VMB_YTDLP_EXTRACTOR_RETRIES",
        "VMB_YTDLP_SOCKET_TIMEOUT",
        "VMB_YTDLP_SLEEP_INTERVAL",
        "VMB_COOKIES_FILE",
        "VMB_COOKIES_BROWSER",
    ):
        monkeypatch.delenv(name, raising=False)


def _value_after(args: list[str], option: str) -> str:
    return args[args.index(option) + 1]


def test_network_args_are_per_platform(monkeypatch):
    _clear_ytdlp_env(monkeypatch)

    bilibili = ytdlp_network_args("https://www.bilibili.com/video/BV1xx")
    douyin = ytdlp_network_args("https://www.douyin.com/video/123")
    xhs = ytdlp_network_args("https://xhslink.cn/abc")
    youtube = ytdlp_network_args("https://youtu.be/abc")
    unknown = ytdlp_network_args("https://example.com/video")

    assert _value_after(bilibili, "--sleep-requests") == "1"
    assert _value_after(douyin, "--sleep-requests") == "2"
    assert _value_after(xhs, "--sleep-requests") == "1.5"
    assert _value_after(youtube, "--sleep-requests") == "0.5"
    assert "--sleep-requests" not in unknown
    assert _value_after(unknown, "--retries") == "3"
    assert _value_after(unknown, "--extractor-retries") == "2"
    assert _value_after(unknown, "--socket-timeout") == "30"


def test_network_args_env_override(monkeypatch):
    _clear_ytdlp_env(monkeypatch)
    monkeypatch.setenv("VMB_YTDLP_SLEEP_REQUESTS", "0.25")
    monkeypatch.setenv("VMB_YTDLP_RETRIES", "1")
    monkeypatch.setenv("VMB_YTDLP_EXTRACTOR_RETRIES", "0")
    monkeypatch.setenv("VMB_YTDLP_SOCKET_TIMEOUT", "12.5")
    monkeypatch.setenv("VMB_YTDLP_SLEEP_INTERVAL", "3")

    args = ytdlp_network_args("https://www.douyin.com/video/123")

    assert _value_after(args, "--sleep-requests") == "0.25"
    assert _value_after(args, "--retries") == "1"
    assert _value_after(args, "--extractor-retries") == "0"
    assert _value_after(args, "--socket-timeout") == "12.5"
    assert _value_after(args, "--sleep-interval") == "3"


def test_cookie_args_file_then_browser(monkeypatch, tmp_path):
    _clear_ytdlp_env(monkeypatch)
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# netscape")
    monkeypatch.setenv("VMB_COOKIES_FILE", str(cookie_file))

    assert ytdlp_cookie_args() == ["--cookies", str(cookie_file)]

    monkeypatch.delenv("VMB_COOKIES_FILE")
    monkeypatch.setenv("VMB_COOKIES_BROWSER", "chrome")
    assert ytdlp_cookie_args() == ["--cookies-from-browser", "chrome"]


def test_ytdlp_extractor_metadata_command_includes_network_args(monkeypatch):
    _clear_ytdlp_env(monkeypatch)
    seen: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout='{"title": "测试"}',
            stderr="",
        )

    monkeypatch.setattr(
        "src.core.extractors.ytdlp_extractor.subprocess.run",
        fake_run,
    )
    extractor = YtDlpExtractor()
    extractor._available = True

    assert extractor._extract_metadata("https://www.douyin.com/video/123")["title"] == "测试"
    cmd = seen["cmd"]
    assert _value_after(cmd, "--sleep-requests") == "2"
    assert _value_after(cmd, "--retries") == "3"
    assert cmd[-1] == "https://www.douyin.com/video/123"


def test_ytdlp_fetcher_command_includes_network_args(monkeypatch, tmp_path):
    _clear_ytdlp_env(monkeypatch)
    seen: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        seen["cmd"] = cmd
        output = tmp_path / "video.m4a"
        output.write_bytes(b"x" * 2048)
        return subprocess.CompletedProcess(cmd, 0, stdout=str(output), stderr="")

    monkeypatch.setattr(
        "src.core.media.ytdlp_fetcher.subprocess.run",
        fake_run,
    )
    fetcher = YtDlpMediaFetcher(ytdlp="/bin/echo")

    fetcher.fetch("https://www.xiaohongshu.com/explore/123", tmp_path)

    assert _value_after(seen["cmd"], "--sleep-requests") == "1.5"


class _OpenCircuitLimiter:
    enabled = True

    def circuit_state(self, platform: str) -> str:
        return "open"


def test_ytdlp_extractor_skips_when_circuit_open(monkeypatch):
    monkeypatch.setattr(
        "src.core.extractors.ytdlp_extractor.get_platform_rate_limiter",
        lambda: _OpenCircuitLimiter(),
    )
    extractor = YtDlpExtractor()
    extractor._available = True

    result = extractor.extract("https://www.bilibili.com/video/BV1xx")

    assert result.success is False
    assert "熔断" in (result.error or "")


def test_ytdlp_asr_skips_when_circuit_open(monkeypatch):
    monkeypatch.setattr(
        "src.core.extractors.ytdlp_asr_extractor.get_platform_rate_limiter",
        lambda: _OpenCircuitLimiter(),
    )
    extractor = YtDlpASRExtractor()
    extractor._available = True

    result = extractor.extract("https://www.bilibili.com/video/BV1xx")

    assert result.success is False
    assert "熔断" in (result.error or "")
