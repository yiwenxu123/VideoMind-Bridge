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
        # 2026-11-20：熔断键与平台名已分离，这里单独记录作用域，
        # 用于断言"抖音直抓打的是 douyin:crawl，不再污染同平台其它链路"。
        self.circuit_keys: list[str | None] = []

    def execute(
        self,
        platform: str,
        func: Any,
        *,
        deadline: float | None = None,
        circuit_key: str | None = None,
    ) -> Any:
        self.calls.append(platform)
        self.circuit_keys.append(circuit_key)
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
    result, failure = extractor._extract_via_gateway(
        "123", "https://www.douyin.com/video/123"
    )

    assert failure is None
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

    title, description, _segments, failure = extractor._fetch_video_data("123")

    assert title == "标题"
    assert description == "描述"
    assert failure is None
    # 平台名仍是 douyin，但熔断作用域应是 douyin:crawl
    assert limiter.calls == ["douyin"]
    assert limiter.circuit_keys == ["douyin:crawl"]


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

    title, content, _, _, _, failure = extractor._fetch_note("note-1")

    assert title == "标题"
    assert content == "这是一段足够长的正文内容"
    assert failure is None
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


def test_douyin_403_is_reported_as_risk_control_without_extra_request():
    """403 必须被识别成"风控"，而不是"没内容"。

    旧断言把 ("", "", None) 写死成契约，等于把"错误归因丢失"固化下来；
    现在失败原因必须显式带出 risk_control，上层才能给出正确处置建议。
    """
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

    assert extractor._fetch_video_data("123") == ("", "", None, "risk_control")
    # 同为 403 时再打 detail API 只会多一次必然失败的请求
    assert len(calls) == 1
    assert "iesdouyin.com" in calls[0]


def _shell_html() -> str:
    """模拟抖音验证码壳页：有反爬标记，但没有任何内容字段。"""
    return (
        "<html><head><title>安全验证</title></head><body>"
        '<div id="captcha_container">请完成滑块验证</div>'
        "<script>window.__secsdk_verify__ = 1; argus.init()</script>"
        "</body></html>"
    )


def test_douyin_shell_page_is_detected_as_risk_control():
    """HTTP 200 的壳页必须判成 risk_control，而不是"成功但无文案"。"""
    limiter = RecordingLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_shell_html())

    extractor = DouyinExtractor(client=_client(handler), limiter=limiter)

    assert extractor._fetch_video_data("123") == ("", "", None, "risk_control")


def test_douyin_normal_page_is_not_mistaken_for_shell():
    """正常页面即使 JS 里出现 verify/captcha 字样，只要内容字段在，就不能误判。"""
    limiter = RecordingLimiter()
    page = (
        '<meta property="og:title" content="标题">'
        '<meta property="og:description" content="' + "正文" * 100 + '">'
        "<script>var captcha_sdk; var verify_flags = {};</script>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=page)

    extractor = DouyinExtractor(client=_client(handler), limiter=limiter)

    title, description, _segments, failure = extractor._fetch_video_data("123")

    assert failure is None
    assert title == "标题"
    assert description.startswith("正文")


# ── 小红书失败归因（2026-11-22）──────────────────────────────────────────
# 背景：`_fetch_note` 曾把异常吞成空元组，上层只能说"可能需要 Cookie"——
# 那是猜测。实测一条真实链接会返回 HTTP 200 空壳页（noteData 只剩 routeQuery、
# 整页无 noteId），与"被风控""需登录"是完全不同的处置。

_SHELL_NOTE = (
    "<html><head><title>- 小红书</title></head><body><script>"
    'window.__INITIAL_STATE__ = {"noteData":{"routeQuery":{"source":"webshare"}}};'
    "</script></body></html>"
)


def test_xhs_shell_page_reports_note_unavailable():
    """200 但整页无 noteId → 笔记不可见，不是风控、更不是"需要 Cookie"。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_SHELL_NOTE)

    extractor = XiaohongshuExtractor(client=_client(handler), limiter=RecordingLimiter())

    assert extractor._fetch_note("note-1")[5] == "note_unavailable"


def test_xhs_soft_404_reports_token_invalid():
    """被导向 /404/sec_ 说明分享参数失效——该提示用户重新分享，而不是让他配 Cookie。"""
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.startswith("/404/"):
            return httpx.Response(
                302, headers={"location": "https://www.xiaohongshu.com/404/sec_abc"}
            )
        return httpx.Response(200, text="<html>not found</html>")

    extractor = XiaohongshuExtractor(client=_client(handler), limiter=RecordingLimiter())

    assert extractor._fetch_note("note-1")[5] == "token_invalid"


def test_xhs_403_maps_to_risk_control():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request)

    injector = PlatformRateLimiter(
        {"xiaohongshu": PlatformPolicy(max_retries=0, circuit_threshold=10)}
    )
    extractor = XiaohongshuExtractor(client=_client(handler), limiter=injector)

    assert extractor._fetch_note("note-1")[5] == "risk_control"


def test_xhs_401_maps_to_login_required():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, request=request)

    injector = PlatformRateLimiter(
        {"xiaohongshu": PlatformPolicy(max_retries=0, circuit_threshold=10)}
    )
    extractor = XiaohongshuExtractor(client=_client(handler), limiter=injector)

    assert extractor._fetch_note("note-1")[5] == "login_required"


def test_xhs_failure_message_does_not_guess_cookie_and_carries_error_code():
    """对外文案不得再出现"可能需要 Cookie"这种猜测，且必须带可机读 error_code。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_SHELL_NOTE)

    extractor = XiaohongshuExtractor(client=_client(handler), limiter=RecordingLimiter())

    result = extractor.extract("https://www.xiaohongshu.com/explore/note-1")

    assert result.success is False
    assert result.error_code == "xhs_note_unavailable"
    assert "Cookie" not in (result.error or ""), f"文案仍在猜测: {result.error}"
    assert "重新分享" in (result.error or ""), f"缺少可执行动作: {result.error}"
