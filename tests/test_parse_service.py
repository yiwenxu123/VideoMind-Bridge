"""parse_service 单元测试 (视频源解析 → 音频中转)"""


import pytest


@pytest.fixture
def media_dir(tmp_path):
    return tmp_path / "media"


def test_get_media_dir_default(monkeypatch, tmp_path):
    monkeypatch.delenv("VMB_MEDIA_DIR", raising=False)
    from src.api.parse_service import get_media_dir

    assert get_media_dir().name == "media"


def test_get_media_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("VMB_MEDIA_DIR", str(tmp_path))
    from src.api.parse_service import get_media_dir

    assert get_media_dir() == tmp_path


def test_cleanup_stale_files(monkeypatch, tmp_path):
    from src.api import parse_service
    from src.api.parse_service import cleanup_stale_files

    monkeypatch.setenv("VMB_MEDIA_DIR", str(tmp_path))
    monkeypatch.setattr(parse_service, "_MEDIA_TTL_SECONDS", 1)
    (tmp_path / "old.m4a").write_bytes(b"x" * 100)
    (tmp_path / "new.m4a").write_bytes(b"y" * 100)
    import os
    import time

    old = tmp_path / "old.m4a"
    now = time.time()
    os.utime(old, (now - 100, now - 100))

    removed = cleanup_stale_files()
    assert removed == 1
    assert not (tmp_path / "old.m4a").exists()
    assert (tmp_path / "new.m4a").exists()


def test_parse_bilibili_playurl_success(monkeypatch):
    """B站 playurl 路径: 官方 API 解析 + 下载中转"""

    from unittest.mock import MagicMock, patch

    from src.api import parse_service

    fake_extractor = MagicMock()
    fake_extractor.get_playurl_audio_urls.return_value = {
        "audio_urls": [
            "https://bad-cdn.example.com/audio.m4s",
            "https://good-cdn.example.com/audio.m4s",
            "https://backup-cdn.example.com/audio.m4s",
        ],
        "title": "测试视频",
        "duration": 120,
    }

    with patch("src.core.extractors.bilibili_extractor.BilibiliExtractor", return_value=fake_extractor), \
         patch("src.api.parse_service._download_to_media") as mock_download, \
         patch("src.api.parse_service.get_media_dir") as mock_dir, \
         patch("src.api.parse_service.cleanup_stale_files"):

        from pathlib import Path as P
        tmp = P("/tmp/vmb_test_media")
        tmp.mkdir(parents=True, exist_ok=True)
        mock_dir.return_value = tmp

        def fake_download(url, media_dir, prefix, headers=None):
            if url.startswith("https://bad-cdn.example.com/"):
                return None
            assert url.startswith("https://good-cdn.example.com/")
            f = media_dir / f"{prefix}-{int(__import__('time').time())}.m4a"
            f.write_bytes(b"\x00" * 1024)
            return f

        mock_download.side_effect = fake_download

        result = parse_service.parse_audio_source("https://www.bilibili.com/video/BV1test1234")
        assert result["success"] is True
        assert result["platform"] == "bilibili"
        assert result["path"].startswith("/media/")
        assert result["duration"] == 120
        assert mock_download.call_count == 2
        first_url = mock_download.call_args_list[0].args[0]
        second_url = mock_download.call_args_list[1].args[0]
        assert first_url.startswith("https://bad-cdn.example.com/")
        assert second_url.startswith("https://good-cdn.example.com/")
        # 清理测试文件
        for f in tmp.iterdir():
            f.unlink()


def test_parse_bilibili_playurl_fallback_to_ytdlp(monkeypatch):
    """B站 playurl 失败时回退 yt-dlp"""
    from unittest.mock import MagicMock, patch

    from src.api.parse_service import _parse_bilibili_playurl

    fake_extractor = MagicMock()
    fake_extractor.get_playurl_audio_urls.return_value = None

    with patch("src.core.extractors.bilibili_extractor.BilibiliExtractor", return_value=fake_extractor):
        result = _parse_bilibili_playurl("https://www.bilibili.com/video/BV1test1234")
        assert result is None
