"""平台提取器只对平台自有请求接入 limiter 的测试。"""

from __future__ import annotations

import json
from typing import Any

import httpx

from src.core.extractors.douyin_extractor import DouyinExtractor
from src.core.extractors.xiaohongshu_extractor import XiaohongshuExtractor
from src.core.extractors.youtube_extractor import YouTubeExtractor
from src.core.platforms.rate_limit import PlatformPolicy, PlatformRateLimiter


class RecordingLimiter(PlatformRateLimiter):
    def __init__(self) -> None:
        super().__init__({}, enabled=True)
        self.calls: list[str] = []

    def execute(
        self,
        platform: str,
        func: Any,
        *,
        deadline: float | None = None,
    ) -> Any:
        self.calls.append(platform)
        return func()


def _client(handler) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )


def test_douyin_gateway_bypasses_platform_limiter():
    limiter = RecordingLimiter()
    detail = {
        "aweme_id": "123",
        "desc": "测试描述" * 20,
        "author": {"nickname": "作者"},
        "duration": 1000,
        "video": {"play_addr": {"url_list": []}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "fetch_one_video" in str(request.url)
        return httpx.Response(200, json={"code": 200, "data": {"aweme_detail": detail}})

    extractor = DouyinExtractor(client=_client(handler), limiter=limiter)
    result = extractor._extract_via_gateway("123", "https://www.douyin.com/video/123")

    assert result is not None
    assert result.success is True
    assert limiter.calls == []


def test_douyin_page_uses_platform_limiter():
    limiter = RecordingLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        assert "iesdouyin.com" in str(request.url)
        return httpx.Response(
            200,
            text=(
                '<meta property="og:title" content="标题">'
                '<meta property="og:description" content="描述">'
            ),
        )

    extractor = DouyinExtractor(client=_client(handler), limiter=limiter)

    title, description, _ = extractor._fetch_video_data("123")

    assert title == "标题"
    assert description == "描述"
    assert limiter.calls == ["douyin"]


def test_douyin_short_link_uses_platform_limiter():
    limiter = RecordingLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "v.douyin.com":
            return httpx.Response(
                302,
                headers={"location": "https://www.douyin.com/video/123"},
            )
        return httpx.Response(200, text="ok")

    extractor = DouyinExtractor(client=_client(handler), limiter=limiter)

    assert extractor._resolve_short_url("https://v.douyin.com/abc") == (
        "https://www.douyin.com/video/123"
    )
    assert limiter.calls == ["douyin"]


def test_xiaohongshu_note_uses_platform_limiter():
    limiter = RecordingLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        assert "xiaohongshu.com" in str(request.url)
        return httpx.Response(
            200,
            text=(
                '<meta property="og:title" content="标题">'
                '<meta property="og:description" content="这是一段足够长的正文内容">'
            ),
        )

    extractor = XiaohongshuExtractor(client=_client(handler), limiter=limiter)

    title, content, _, _, _ = extractor._fetch_note("note-1")

    assert title == "标题"
    assert content == "这是一段足够长的正文内容"
    assert limiter.calls == ["xiaohongshu"]


def test_youtube_oembed_uses_platform_limiter():
    limiter = RecordingLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        assert "youtube.com/oembed" in str(request.url)
        return httpx.Response(200, json={"title": "标题"})

    extractor = YouTubeExtractor(client=_client(handler), limiter=limiter)

    assert extractor._get_title("dQw4w9WgXcQ") == "标题"
    assert limiter.calls == ["youtube"]


def test_youtube_third_party_transcript_bypasses_limiter():
    limiter = RecordingLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "youtubetranscript.com"
        return httpx.Response(
            200,
            content=json.dumps(
                [{"text": "hello", "start": 0, "duration": 1}]
            ).encode(),
        )

    extractor = YouTubeExtractor(client=_client(handler), limiter=limiter)

    text, segments, language = extractor._get_transcript("dQw4w9WgXcQ")

    assert text == "hello"
    assert segments[0]["text"] == "hello"
    assert language == "en"
    assert limiter.calls == []


def test_douyin_risk_control_does_not_fall_back_to_detail_api():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(403, request=request)

    extractor = DouyinExtractor(
        client=_client(handler),
        limiter=PlatformRateLimiter(
            {"douyin": PlatformPolicy(max_retries=0, circuit_threshold=10)}
        ),
    )

    assert extractor._fetch_video_data("123") == ("", "", None)
    assert len(calls) == 1
    assert "iesdouyin.com" in calls[0]
