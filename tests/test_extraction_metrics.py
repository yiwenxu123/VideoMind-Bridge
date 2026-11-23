"""提取链路命中分布指标测试（2026-11-23）。

这套指标存在的意义是回答三个运维问题：
1. 抖音这些请求里，多少走 ASR、多少走字幕？
2. 失败主要卡在哪一环（网关不可达 / 视频不可见 / 真风控）？
3. 哪条链路其实从没被用到（白白维护）？

设计上两条纪律：
- **缓存命中单独计**，否则 ASR 占比会被缓存放大成虚假繁荣；
- **键空间有上限**，错误码意外爆炸不会让内存无限增长。
"""

from __future__ import annotations

import pytest

from src.core.metrics import ExtractionMetrics, get_extraction_metrics, reset_extraction_metrics
from src.core.models import CostTier, ExtractResult


def _result(
    *,
    success: bool = True,
    method: str = "asr",
    source: str = "douyin_asr",
    platform: str = "douyin",
    completeness: str = "full",
    error_code: str | None = None,
) -> ExtractResult:
    return ExtractResult(
        success=success,
        platform=platform,
        title="t",
        content="正文内容",
        source=source,
        url="https://example.com/v",
        cost_tier=CostTier.CHEAP,
        method=method,
        completeness=completeness,
        error_code=error_code,
    )


@pytest.fixture(autouse=True)
def _fresh_singleton():
    reset_extraction_metrics()
    yield
    reset_extraction_metrics()


def test_counts_by_method_source_platform():
    m = ExtractionMetrics()
    m.record(_result(method="asr", source="douyin_asr"))
    m.record(_result(method="asr", source="ytdlp_asr_local"))
    m.record(_result(method="subtitle", source="bilibili_api", platform="bilibili"))

    snap = m.snapshot()
    assert snap["total"] == 3
    assert snap["method"] == {"asr": 2, "subtitle": 1}
    assert snap["source"]["bilibili_api"] == 1
    assert snap["platform"] == {"douyin": 2, "bilibili": 1}


def test_method_share_answers_asr_vs_subtitle():
    """最常用的派生值：转写与字幕各占多少。"""
    m = ExtractionMetrics()
    for _ in range(3):
        m.record(_result(method="asr"))
    m.record(_result(method="subtitle", source="bilibili_api", platform="bilibili"))

    share = m.snapshot()["method_share"]
    assert share["total_classified"] == 4
    assert share["asr"] == 0.75
    assert share["subtitle"] == 0.25


def test_cache_hits_counted_separately():
    """缓存命中必须单独计，且不能算进 method 分布（否则 ASR 占比虚高）。"""
    m = ExtractionMetrics()
    m.record(_result(method="asr"))
    m.record(_result(method="asr"), cache_hit=True)

    snap = m.snapshot()
    assert snap["total"] == 2
    assert snap["cache_hits"] == 1
    assert snap["method"] == {"asr": 1}


def test_failure_error_codes_distributed():
    m = ExtractionMetrics()
    m.record(_result(success=False, completeness="none", error_code="douyin_gateway_unavailable"))
    m.record(_result(success=False, completeness="none", error_code="douyin_gateway_unavailable"))
    m.record(_result(success=False, completeness="none", error_code="douyin_gateway_no_detail"))

    snap = m.snapshot()
    assert snap["error_code"] == {
        "douyin_gateway_unavailable": 2,
        "douyin_gateway_no_detail": 1,
    }
    assert snap["completeness"]["none"] == 3


def test_success_does_not_pollute_error_codes():
    m = ExtractionMetrics()
    m.record(_result(success=True, error_code=None))
    assert m.snapshot()["error_code"] == {}


def test_unknown_values_are_labelled():
    m = ExtractionMetrics()
    m.record(_result(method="", source="", platform="", completeness=""))
    snap = m.snapshot()
    assert snap["method"] == {"unknown": 1}
    assert snap["source"] == {"unknown": 1}


def test_key_space_is_bounded():
    """异常情况下错误码可能五花八门，不能让它无限增长。"""
    m = ExtractionMetrics()
    for i in range(200):
        m.record(_result(success=False, error_code=f"code_{i}"))
    codes = m.snapshot()["error_code"]
    assert len(codes) <= 41, f"键空间未受限: {len(codes)}"
    assert codes.get("other", 0) > 0


def test_singleton_is_shared_and_resettable():
    a = get_extraction_metrics()
    a.record(_result())
    assert get_extraction_metrics().snapshot()["total"] == 1
    reset_extraction_metrics()
    assert get_extraction_metrics().snapshot()["total"] == 0


# ── 运行时级：确认指标真的被记录（而不只是计数器本身能用）──────────────


class _StubExtractor:
    platform_name = "douyin"

    def __init__(self, result: ExtractResult) -> None:
        self.result = result
        self.calls = 0

    def supports(self, url: str) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def extract(self, url: str, _options=None) -> ExtractResult:
        self.calls += 1
        return self.result

    def close(self) -> None:
        pass


def test_runtime_records_real_extraction_and_cache_hit():
    """跑两次：第一次真提取，第二次命中缓存，指标要能区分。"""
    from src.core.router import ContentRouter, RouterConfig
    from src.core.router_runtime import RouterRuntime

    stub = _StubExtractor(_result(method="asr", source="douyin_asr"))
    router = ContentRouter(RouterConfig(priority=["fake"], use_cache=False))
    router._extractor_classes = {"fake": lambda: stub}
    runtime = RouterRuntime(router=router)
    try:
        runtime.extract("https://www.douyin.com/video/7400000000000000001")
        runtime.extract("https://www.douyin.com/video/7400000000000000001")
    finally:
        runtime.close()

    snap = get_extraction_metrics().snapshot()
    assert snap["total"] == 2
    assert snap["cache_hits"] == 1
    assert snap["extracted"] == 1
    assert snap["method"] == {"asr": 1}, "缓存命中不得计入 method 分布"
    assert stub.calls == 1


def test_runtime_records_failure_error_code():
    from src.core.router import ContentRouter, RouterConfig
    from src.core.router_runtime import RouterRuntime

    failure = _result(
        success=False,
        method="desc",
        source="douyin",
        completeness="none",
        error_code="douyin_gateway_unavailable",
    )
    router = ContentRouter(RouterConfig(priority=["fake"], use_cache=False))
    router._extractor_classes = {"fake": lambda: _StubExtractor(failure)}
    runtime = RouterRuntime(router=router)
    try:
        runtime.extract("https://www.douyin.com/video/7400000000000000002")
    finally:
        runtime.close()

    snap = get_extraction_metrics().snapshot()
    assert snap["error_code"] == {"douyin_gateway_unavailable": 1}
    assert snap["completeness"] == {"none": 1}
