"""对外契约测试（2026-11-23）。

## 为什么需要这个文件

本服务有一个**真实下游**：`内容运营agent/api-server/services/VideoMindClient.js`。
它依赖两条隐含约定，任何一条被改动都会让下游静默降级或直接抛 502：

1. **`success` 表示"拿到东西了"，不是"内容完整"**。
   下游写的是 `if (data.success !== true) throw ...（502）`，
   完整性由 `completeness` 表达，下游自己还有一层"completeness=full 是否可信"的
   密度校验（内容字数 / 时长 < 1.5 字秒 → 降级 partial）。
   → 所以"只拿到标题/文案"这类部分结果**必须 success=true + completeness=meta**。
   曾有一版把它改成 success=false 以"不谎报成功"，结果是下游把唯一可用内容当硬错误。

2. **小红书正文的装配形状**是 `title + "\\n\\n" + 正文`（标题另放 `title`）。
   下游会检测 content 以 title 开头并紧跟空白，然后把标题前缀剥掉，避免重复拼接。
   → 形状变了（比如改成只回正文、或改用别的分隔）会让下游剥不掉、下游再拼标题就重复。

这个文件把这些约定锁在**服务方**，而不是只活在下游的注释里。
对应业界做法是 consumer-driven contract testing 的最轻形态：把下游的解析假设
复制成提供方的断言。
"""

from __future__ import annotations

import httpx

from src.core.extractors.xiaohongshu_extractor import XiaohongshuExtractor
from src.core.models import CostTier, ExtractResult
from src.core.router import ContentRouter, RouterConfig


def _partial_result() -> ExtractResult:
    return ExtractResult(
        success=True,
        platform="douyin",
        title="标题",
        content="只拿到的一段文案",
        source="douyin_gateway",
        url="https://www.douyin.com/video/1",
        cost_tier=CostTier.FREE,
        is_placeholder=True,
        completeness="meta",
        method="desc",
        metadata={"partial_content": True},
        error="仅取到抖音文案/标题，非视频全文",
    )


class _Stub:
    def __init__(self, result_factory, name="douyin") -> None:
        self._factory = result_factory
        self.platform_name = name

    def supports(self, url: str) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def extract(self, url: str, _options=None) -> ExtractResult:
        return self._factory()

    def close(self) -> None:
        pass


def _run(priority, classes, url="https://www.douyin.com/video/7400000000000000009"):
    router = ContentRouter(RouterConfig(priority=priority, use_cache=False))
    router._extractor_classes = classes
    try:
        return router.extract(url)
    finally:
        router.close()


def test_partial_content_is_success_with_meta_completeness():
    """部分内容必须 success=true + completeness=meta。

    下游 VideoMindClient.js 对 success!==true 直接抛 502；把部分内容标成失败，
    会让"能用的文案"退化成硬错误。
    """
    result = _run(
        ["douyin", "ytdlp_asr"],
        {
            "douyin": _PartialStub,
            "ytdlp_asr": _FailStub,
        },
    )

    assert result.success is True, "下游以 success!==true 为致命错误"
    assert result.completeness == "meta", "完整性通过 completeness 表达"
    assert result.content.strip(), "部分内容不能丢"
    assert result.metadata.get("partial") is True, "下游可据此提示用户内容不完整"


def test_hard_failure_is_success_false_with_error_code():
    """彻底失败时 success=false 且必须带可机读 error_code（下游用它映射 HTTP 状态）。"""
    result = _run(
        ["douyin"],
        {"douyin": _FailStub},
        url="https://www.douyin.com/video/7400000000000000010",
    )

    assert result.success is False
    assert result.error_code, "下游靠 error_code 区分 422/502"
    assert "attempts" in (result.metadata or {}), "失败明细要留在 metadata 里便于排查"


def test_xiaohongshu_content_shape_keeps_title_prefix():
    """小红书正文形状 `title + "\\n\\n" + 正文` 是对下游的既有约定（下游会剥前缀）。

    形状一变，下游剥不掉标题前缀，再拼一次标题就会重复。
    """
    body = "这是笔记正文内容，足够长以便通过提取门槛。"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                '<meta property="og:title" content="我的标题">'
                f'<meta property="og:description" content="{body}">'
            ),
        )

    from tests.test_extractor_platform_limits import RecordingLimiter

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    extractor = XiaohongshuExtractor(client=client, limiter=RecordingLimiter())
    result = extractor.extract("https://www.xiaohongshu.com/explore/note-1")

    assert result.success is True
    assert result.title == "我的标题"
    assert result.content.startswith("我的标题"), "下游依赖 content 以 title 开头来剥前缀"
    assert result.content[len("我的标题")].isspace(), "前缀后必须紧跟空白，下游才敢剥"


class _PartialStub(_Stub):
    def __init__(self) -> None:
        super().__init__(_partial_result)


class _FailStub(_Stub):
    def __init__(self) -> None:
        super().__init__(_failure, name="ytdlp_asr")


def _failure() -> ExtractResult:
    return ExtractResult(
        success=False,
        platform="ytdlp_asr",
        title="",
        content="",
        source="ytdlp_asr",
        url="https://www.douyin.com/video/1",
        cost_tier=CostTier.CHEAP,
        error="下载失败",
        error_code="ytdlp_download_failed",
    )


# ── CONTRACT.md §4 的不变式 ─────────────────────────────────────────────
# 文档写的不变式必须有测试兜着，否则就是口号。


def _assert_invariants(result):
    if result.success is False:
        assert result.error_code, "不变式 1：失败必须带可机读 error_code"
    else:
        assert result.completeness in {"full", "meta"}, (
            f"不变式 2：success=true 时 completeness 不得为 {result.completeness!r}"
        )
    if result.completeness == "full":
        assert (result.content or "").strip(), "不变式 3：full 必须有正文"


def test_invariants_hold_for_partial_result():
    _assert_invariants(
        _run(["douyin", "ytdlp_asr"], {"douyin": _PartialStub, "ytdlp_asr": _FailStub})
    )


def test_invariants_hold_for_hard_failure():
    _assert_invariants(
        _run(["douyin"], {"douyin": _FailStub}, url="https://www.douyin.com/video/7400000000000000011")
    )


def test_invariants_hold_for_full_success():
    def _full() -> ExtractResult:
        return ExtractResult(
            success=True,
            platform="douyin",
            title="标题",
            content="正文" * 60,
            source="douyin_asr",
            url="https://www.douyin.com/video/1",
            cost_tier=CostTier.CHEAP,
            completeness="full",
            method="asr",
        )

    result = _run(
        ["douyin"],
        {"douyin": lambda: _Stub(_full)},
        url="https://www.douyin.com/video/7400000000000000012",
    )
    _assert_invariants(result)
    assert result.completeness == "full"
