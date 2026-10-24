"""本地媒体文件识别与 API 白名单校验测试。"""

import pytest

from src.services.local_media import (
    is_local_media_path,
    is_remote_url,
    resolve_allowed_local_media_path,
    resolve_local_media_path,
)
from src.utils.exceptions import ValidationError


def test_is_remote_url():
    assert is_remote_url("https://example.com/video")
    assert is_remote_url("HTTP://example.com/video")
    assert not is_remote_url("/tmp/video.mp4")


def test_is_local_media_path_supported(tmp_path):
    video = tmp_path / "clip.mp4"
    audio = tmp_path / "voice.m4a"
    video.write_bytes(b"x")
    audio.write_bytes(b"x")
    assert is_local_media_path(str(video))
    assert is_local_media_path(str(audio))


def test_is_local_media_path_rejects_missing_url_and_unknown_suffix(tmp_path):
    assert not is_local_media_path(str(tmp_path / "missing.mp4"))
    assert not is_local_media_path("https://example.com/video.mp4")
    unknown = tmp_path / "notes.txt"
    unknown.write_bytes(b"x")
    assert not is_local_media_path(str(unknown))


def test_resolve_local_media_path_missing_raises(tmp_path):
    with pytest.raises(ValidationError) as exc:
        resolve_local_media_path(str(tmp_path / "missing.mp4"))
    assert exc.value.error_code == "INVALID_PATH"


def test_resolve_local_media_path_unknown_suffix_raises(tmp_path):
    unknown = tmp_path / "notes.txt"
    unknown.write_bytes(b"x")
    with pytest.raises(ValidationError) as exc:
        resolve_local_media_path(str(unknown))
    assert exc.value.error_code == "INVALID_PATH"


def test_allowed_local_path_requires_config(tmp_path, monkeypatch):
    monkeypatch.delenv("VMB_LOCAL_MEDIA_DIRS", raising=False)
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"x")

    with pytest.raises(ValidationError) as exc:
        resolve_allowed_local_media_path(str(media))
    assert exc.value.error_code == "LOCAL_PATH_NOT_ALLOWED"


def test_allowed_local_path_inside_root(tmp_path, monkeypatch):
    monkeypatch.setenv("VMB_LOCAL_MEDIA_DIRS", str(tmp_path))
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"x")

    assert resolve_allowed_local_media_path(str(media)) == media.resolve()


def test_allowed_local_path_outside_root(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("VMB_LOCAL_MEDIA_DIRS", str(allowed))
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"x")

    with pytest.raises(ValidationError) as exc:
        resolve_allowed_local_media_path(str(media))
    assert exc.value.error_code == "LOCAL_PATH_NOT_ALLOWED"
