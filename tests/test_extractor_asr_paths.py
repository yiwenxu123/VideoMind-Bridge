"""抖音网关 ASR 与小红书视频 ASR 路径测试。"""

from __future__ import annotations

import json
from unittest import mock

from src.core.asr import Segment, Transcript
from src.core.extractors import douyin_extractor as douyin_mod
from src.core.extractors import xiaohongshu_extractor as xhs_mod
from src.core.extractors.douyin_extractor import DouyinExtractor
from src.core.extractors.xiaohongshu_extractor import XiaohongshuExtractor
from src.core.media import FetchedMedia, MediaFetchFailed
from src.core.models import ExtractOptions


def _transcript(text: str = "口播内容" * 20) -> Transcript:
    return Transcript(
        text=text,
        provider="sensevoice",
        model="sensevoice-small",
        language="zh",
        segments=[Segment(start=0.0, end=1.0, text="口播内容")],
    )


def _gateway_response() -> mock.Mock:
    detail = {
        "aweme_id": "123456789012345",
        "desc": "抖音测试描述" * 10,
        "author": {"nickname": "测试作者"},
        "duration": 60000,
        "video": {"play_addr": {"url_list": ["https://cdn.example/video.mp4"]}},
    }
    response = mock.Mock()
    response.json.return_value = {"code": 200, "data": {"aweme_detail": detail}}
    return response


def test_douyin_gateway_asr_full(monkeypatch, tmp_path):
    extractor = DouyinExtractor()
    audio = tmp_path / "video.mp4"
    audio.write_bytes(b"x" * 2048)
    transcript = _transcript("抖音口播" * 20)

    monkeypatch.setattr(extractor._client, "get", lambda *a, **k: _gateway_response())
    monkeypatch.setattr(
        douyin_mod.HttpMediaFetcher,
        "fetch",
        lambda self, request: FetchedMedia(path=audio, size=2048),
    )
    monkeypatch.setattr(douyin_mod, "transcribe_with_chain", lambda *a, **k: transcript)

    result = extractor.extract(
        "https://www.douyin.com/video/123456789012345",
        ExtractOptions(asr_language="zh"),
    )

    assert result.success is True
    assert result.completeness == "full"
    assert result.method == "asr"
    assert result.content == transcript.text
    assert result.asr_provider == "sensevoice"
    assert result.metadata["aweme_id"] == "123456789012345"
    assert result.metadata["api_provider"] == "sensevoice_asr"


def test_douyin_gateway_meta_when_download_fails(monkeypatch):
    extractor = DouyinExtractor()
    monkeypatch.setattr(extractor._client, "get", lambda *a, **k: _gateway_response())

    def _fail(self, request):
        raise MediaFetchFailed("cdn blocked")

    monkeypatch.setattr(douyin_mod.HttpMediaFetcher, "fetch", _fail)

    result = extractor.extract("https://www.douyin.com/video/123456789012345")

    assert result.success is True
    assert result.completeness == "meta"
    assert result.method == "desc"
    assert "抖音测试描述" in result.content


def _xhs_video_html() -> str:
    state = {
        "note": {
            "noteDetailMap": {
                "note-1": {
                    "note": {
                        "noteId": "note-1",
                        "title": "小红书视频标题",
                        "desc": "发布文案",
                        "type": "video",
                        "user": {"nickname": "作者"},
                        "video": {
                            "duration": 60000,
                            "media": {
                                "stream": {
                                    "h264": [
                                        {
                                            "videoBitrate": 1000,
                                            "masterUrl": "https://cdn.example/low.mp4",
                                        },
                                        {
                                            "videoBitrate": 3000,
                                            "masterUrl": "https://cdn.example/high.mp4",
                                            "backupUrls": ["https://cdn.example/backup.mp4"],
                                        },
                                    ]
                                }
                            },
                        },
                    }
                }
            }
        }
    }
    return (
        "<html><script>window.__INITIAL_STATE__="
        + json.dumps(state, ensure_ascii=False)
        + "</script></html>"
    )


def test_xhs_video_urls_prefer_highest_bitrate():
    note = XiaohongshuExtractor._find_note_payload(
        json.loads(
            _xhs_video_html()
            .split("window.__INITIAL_STATE__=", 1)[1]
            .split("</script>", 1)[0]
        )
    )
    urls = XiaohongshuExtractor._extract_video_urls(note)
    assert urls == ["https://cdn.example/high.mp4", "https://cdn.example/backup.mp4"]


def test_xhs_video_asr_full(monkeypatch, tmp_path):
    extractor = XiaohongshuExtractor()
    audio = tmp_path / "video.mp4"
    audio.write_bytes(b"x" * 2048)
    transcript = _transcript("小红书口播" * 20)

    monkeypatch.setattr(
        xhs_mod.HttpMediaFetcher,
        "fetch",
        lambda self, request: FetchedMedia(path=audio, size=2048),
    )
    monkeypatch.setattr(xhs_mod, "transcribe_with_chain", lambda *a, **k: transcript)

    result = extractor._try_video_asr(
        _xhs_video_html(),
        "https://www.xiaohongshu.com/explore/note-1",
        "note-1",
        "小红书视频标题",
        "发布文案",
        ExtractOptions(),
    )

    assert result is not None
    assert result.success is True
    assert result.completeness == "full"
    assert result.method == "asr"
    assert result.content == transcript.text
    assert result.metadata["note_id"] == "note-1"
    assert result.metadata["api_provider"] == "sensevoice_asr"


def test_xhs_old_note_structure_payload():
    state = {
        "noteData": {
            "data": {
                "noteData": {
                    "title": "旧结构标题",
                    "desc": "旧结构正文",
                    "type": "normal",
                }
            }
        }
    }
    note = XiaohongshuExtractor._find_note_payload(state)
    assert note["title"] == "旧结构标题"
    assert note["desc"] == "旧结构正文"
