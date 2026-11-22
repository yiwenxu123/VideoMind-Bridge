"""URL 归一化测试（2026-11-22）。

锁住"抖音第一坑"：`jingxuan?modal_id=<id>` 这类写法必须被收敛成 `/video/<id>`，
否则 yt-dlp 报 `Unsupported URL`，而该报错会被上层误读成"风控"。
"""

from __future__ import annotations

import pytest

from src.utils.url_normalize import normalize_video_url

_VIDEO_ID = "7640637984061484998"
_CANONICAL = f"https://www.douyin.com/video/{_VIDEO_ID}"


@pytest.mark.parametrize(
    "raw",
    [
        f"https://www.douyin.com/jingxuan?modal_id={_VIDEO_ID}",
        f"https://www.douyin.com/user/MS4wLjABAAAA?modal_id={_VIDEO_ID}",
        f"https://www.douyin.com/video/{_VIDEO_ID}",
        f"https://www.douyin.com/video/{_VIDEO_ID}?previous_page=app_code_link",
        f"https://www.iesdouyin.com/share/video/{_VIDEO_ID}/",
        f"https://www.iesdouyin.com/share/video/{_VIDEO_ID}/?region=CN&mid=1",
        f"https://www.douyin.com/share/video/{_VIDEO_ID}",
        f"  https://www.douyin.com/jingxuan?modal_id={_VIDEO_ID}  ",
    ],
)
def test_douyin_forms_converge_to_canonical(raw: str) -> None:
    assert normalize_video_url(raw) == _CANONICAL


def test_fragment_is_stripped() -> None:
    assert normalize_video_url(f"{_CANONICAL}#comment") == _CANONICAL


@pytest.mark.parametrize(
    "raw",
    [
        # 短链需要 302 才知道目标，归一化是纯函数，不能在这里猜
        "https://v.douyin.com/kDF2hXSzlHw/",
        # 其它平台不在此函数职责内，必须原样返回
        "https://www.bilibili.com/video/BV1p45v6kEJc/",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://example.com/video/123",
    ],
)
def test_unknown_or_short_links_are_left_untouched(raw: str) -> None:
    assert normalize_video_url(raw) == raw


def test_idempotent() -> None:
    once = normalize_video_url(f"https://www.douyin.com/jingxuan?modal_id={_VIDEO_ID}")
    assert normalize_video_url(once) == once


def test_empty_input_safe() -> None:
    assert normalize_video_url("") == ""
    assert normalize_video_url("   ") == ""


# ── 路由层：归一化必须发生在提取器之前 ──────────────────────────────────


def test_router_passes_canonical_url_to_extractors():
    """提取器收到的必须是归一化后的 URL，而不是原始的 jingxuan?modal_id=。"""
    from src.core.models import CostTier, ExtractResult
    from src.core.router import ContentRouter, RouterConfig

    seen: list[str] = []

    class _Recorder:
        platform_name = "fake"

        def supports(self, url: str) -> bool:
            return True

        def is_available(self) -> bool:
            return True

        def extract(self, url, _options=None):
            seen.append(url)
            return ExtractResult(
                success=False,
                platform="fake",
                title="",
                content="",
                source="fake",
                url=url,
                cost_tier=CostTier.FREE,
                error="只用于记录入参",
            )

        def close(self) -> None:
            pass

    router = ContentRouter(RouterConfig(priority=["fake"], use_cache=False))
    router._extractor_classes = {"fake": _Recorder}
    try:
        router.extract(f"https://www.douyin.com/jingxuan?modal_id={_VIDEO_ID}")
    finally:
        router.close()

    assert seen == [_CANONICAL], f"提取器收到的 URL 未归一化: {seen}"
