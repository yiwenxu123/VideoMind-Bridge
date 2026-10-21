"""RouterRuntime 的缓存、成本 key、状态缓存与关闭测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.cache import TTLCache
from src.core.models import CostTier, ExtractOptions, ExtractResult
from src.core.router_runtime import RouterRuntime


def _result(completeness: str = "full", request_id: str = "r1") -> ExtractResult:
    return ExtractResult(
        success=True,
        platform="mock",
        title="标题",
        content="正文",
        source="mock",
        url="https://example.com/v",
        cost_tier=CostTier.FREE,
        completeness=completeness,
        request_id=request_id,
    )


def test_runtime_reuses_cache_and_updates_request_id():
    router = MagicMock()
    router.extract.return_value = _result()
    runtime = RouterRuntime(router=router, cache=TTLCache(), cache_ttl=60)

    first = runtime.extract("https://example.com/v", max_cost=CostTier.CHEAP)
    second = runtime.extract(
        "https://example.com/v",
        max_cost=CostTier.CHEAP,
        options=ExtractOptions(request_id="r2"),
    )

    assert router.extract.call_count == 1
    assert first.request_id == "r1"
    assert second.request_id == "r2"


def test_runtime_cache_key_includes_options_and_cost():
    router = MagicMock()
    router.extract.return_value = _result()
    runtime = RouterRuntime(router=router, cache=TTLCache(), cache_ttl=60)

    runtime.extract(
        "https://example.com/v",
        max_cost=CostTier.CHEAP,
        options=ExtractOptions(asr_chain=["sensevoice"]),
    )
    runtime.extract(
        "https://example.com/v",
        max_cost=CostTier.CHEAP,
        options=ExtractOptions(asr_chain=["dashscope"]),
    )
    runtime.extract("https://example.com/v", max_cost=CostTier.PREMIUM)

    assert router.extract.call_count == 3


def test_runtime_does_not_cache_meta_results():
    router = MagicMock()
    router.extract.return_value = _result(completeness="meta")
    runtime = RouterRuntime(router=router, cache=TTLCache(), cache_ttl=60)

    runtime.extract("https://example.com/v", max_cost=CostTier.CHEAP)
    runtime.extract("https://example.com/v", max_cost=CostTier.CHEAP)

    assert router.extract.call_count == 2


def test_runtime_status_cache_and_close():
    router = MagicMock()
    router.list_extractors.return_value = {"mock": True}
    runtime = RouterRuntime(router=router, cache=TTLCache())

    assert runtime.extractor_status() == {"mock": True}
    assert runtime.extractor_status() == {"mock": True}
    assert router.list_extractors.call_count == 1

    runtime.close()
    router.close.assert_called_once()
