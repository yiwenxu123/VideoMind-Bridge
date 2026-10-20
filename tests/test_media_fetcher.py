"""MediaFetcher 与共享音频转码测试（阶段 3）。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import httpx
import pytest

from src.core.media import (
    HttpMediaFetcher,
    MediaFetchFailed,
    MediaFetchRequest,
    MediaTooLarge,
    MediaTranscodeError,
    YtDlpMediaFetcher,
    transcode_to_mp3,
)


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_http_fetcher_downloads_with_headers(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["referer"] = request.headers.get("referer")
        return httpx.Response(200, content=b"x" * 2048, headers={"content-type": "audio/m4s"})

    dest = tmp_path / "audio.m4s"
    media = HttpMediaFetcher(_mock_client(handler)).fetch(
        MediaFetchRequest(
            url="https://cdn.example/audio.m4s",
            dest=dest,
            headers={"Referer": "https://www.bilibili.com/"},
        )
    )

    assert seen["referer"] == "https://www.bilibili.com/"
    assert media.path == dest
    assert media.size == 2048
    assert media.content_type == "audio/m4s"
    assert dest.read_bytes() == b"x" * 2048


def test_http_fetcher_rejects_oversized_and_cleans_partial(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 4096)

    dest = tmp_path / "too-large.m4s"
    with pytest.raises(MediaTooLarge):
        HttpMediaFetcher(_mock_client(handler)).fetch(
            MediaFetchRequest(url="https://cdn.example/a", dest=dest, max_bytes=1024)
        )
    assert not dest.exists()


def test_http_fetcher_rejects_too_small_and_cleans(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x")

    dest = tmp_path / "tiny.m4s"
    with pytest.raises(MediaFetchFailed):
        HttpMediaFetcher(_mock_client(handler)).fetch(
            MediaFetchRequest(url="https://cdn.example/a", dest=dest, min_bytes=1000)
        )
    assert not dest.exists()


def test_ytdlp_raw_download(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        output = tmp_path / "video.m4a"
        output.write_bytes(b"x" * 2048)
        return subprocess.CompletedProcess(cmd, 0, stdout=str(output), stderr="")

    monkeypatch.setattr("src.core.media.ytdlp_fetcher.subprocess.run", fake_run)
    fetcher = YtDlpMediaFetcher(ytdlp="/bin/echo")

    media = fetcher.fetch("https://example.com/video", tmp_path)

    assert media.path.name == "video.m4a"
    assert media.size == 2048
    assert media.source == "yt-dlp-raw"


def test_ytdlp_transcode_fallback(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        if "--extract-audio" in cmd:
            (tmp_path / "audio.mp3").write_bytes(b"x" * 2048)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="raw failed")

    monkeypatch.setattr("src.core.media.ytdlp_fetcher.subprocess.run", fake_run)
    monkeypatch.setattr("src.core.media.ytdlp_fetcher.find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    fetcher = YtDlpMediaFetcher(ytdlp="/bin/echo")

    media = fetcher.fetch("https://example.com/video", tmp_path)

    assert media.path.name == "audio.mp3"
    assert media.source == "yt-dlp-transcoded"


def test_ytdlp_cookies_file_takes_precedence(tmp_path, monkeypatch):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# netscape")
    monkeypatch.setenv("VMB_COOKIES_FILE", str(cookie_file))
    fetcher = YtDlpMediaFetcher(ytdlp="/bin/echo")

    assert fetcher._cookies_args() == ["--cookies", str(cookie_file)]


def test_ytdlp_dump_metadata_parses_json(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout='{"title": "测试", "duration": 60}', stderr="")

    monkeypatch.setattr("src.core.media.ytdlp_fetcher.subprocess.run", fake_run)
    fetcher = YtDlpMediaFetcher(ytdlp="/bin/echo")

    assert fetcher.dump_metadata("https://example.com/v")["title"] == "测试"


def test_transcode_to_mp3_uses_ffmpeg_and_cleans_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.media.audio.find_ffmpeg", lambda: "/usr/bin/ffmpeg")

    def ok_run(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"x" * 2048)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("src.core.media.audio.subprocess.run", ok_run)
    src = tmp_path / "audio.m4s"
    src.write_bytes(b"x")
    out = transcode_to_mp3(src, tmp_path / "audio.mp3")
    assert out.exists()

    def fail_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

    monkeypatch.setattr("src.core.media.audio.subprocess.run", fail_run)
    failed = tmp_path / "failed.mp3"
    with pytest.raises(MediaTranscodeError):
        transcode_to_mp3(src, failed)
    assert not failed.exists()


def test_transcode_without_ffmpeg_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.media.audio.find_ffmpeg", lambda: None)
    with pytest.raises(MediaTranscodeError):
        transcode_to_mp3(tmp_path / "a.m4s", tmp_path / "a.mp3")
