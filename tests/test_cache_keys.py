"""缓存语义测试（2026-11-22）。

修的是一个真实但隐蔽的正确性问题：项目里曾有**两层缓存**，语义不一致。

- `RouterRuntime`（进程级，API/MCP 走它）：键含 成本档/ASR链/语言，只缓存 `full`；
- `ContentRouter` 自己的 `config.cache`：**键只有 URL**，且把 `completeness="meta"`
  （只拿到标题/文案）也当成功缓存。

后果：同一进程内第二次提取同一 URL 时，会被第一次的 meta 结果挡住，
不再尝试更贵的 ASR 路径——明明能拿全文，却返回标题。

处理：默认关闭路由层缓存（单一缓存层），并让写入条件与 RouterRuntime 对齐。
"""

from __future__ import annotations

from typing import Any

from src.core.models import CostTier, ExtractOptions, ExtractResult
from src.core.router import ContentRouter, RouterConfig
from src.core.router_runtime import RouterRuntime

_URL = "https://www.douyin.com/video/7400000000000000000"


class _FixedExtractor:
    """按给定 completeness 返回结果的假提取器。"""

    platform_name = "fake"

    def __init__(self, completeness: str, content: str = "正文" * 80) -> None:
        self.completeness = completeness
        self.content = content
        self.calls = 0

    def supports(self, url: str) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def extract(self, url: str, _options: Any = None) -> ExtractResult:
        self.calls += 1
        return ExtractResult(
            success=True,
            platform="fake",
            title="标题",
            content=self.content,
            source="fake",
            url=url,
            cost_tier=CostTier.FREE,
            completeness=self.completeness,
            method="desc",
        )

    def close(self) -> None:
        pass


def _router(extractor: _FixedExtractor, *, use_cache: bool) -> ContentRouter:
    router = ContentRouter(RouterConfig(priority=["fake"], use_cache=use_cache))
    router._extractor_classes = {"fake": lambda: extractor}
    return router


def test_use_cache_defaults_to_off():
    """默认关闭：进程级缓存应由 RouterRuntime 唯一负责。"""
    assert RouterConfig().use_cache is False


def test_meta_result_is_not_cached():
    """即使显式开启缓存，completeness=meta 也不得写入。

    这是关键回归：曾被缓存后，同进程内更贵的 ASR 尝试会被静默跳过。
    """
    extractor = _FixedExtractor(completeness="meta", content="很短的标题文案")
    router = _router(extractor, use_cache=True)
    try:
        router.extract(_URL)
        assert router.config.cache == {}, "meta 结果不应进缓存"
        # 第二次仍应真正调用提取器
        router.extract(_URL)
        assert extractor.calls == 2
    finally:
        router.close()


def test_full_result_is_cached_when_enabled():
    extractor = _FixedExtractor(completeness="full")
    router = _router(extractor, use_cache=True)
    try:
        router.extract(_URL)
        assert _URL in router.config.cache
        router.extract(_URL)
        assert extractor.calls == 1, "full 结果应命中缓存，不再调用提取器"
    finally:
        router.close()


# ── 运行时缓存键：必须包含影响转写结果的模型维度 ──────────────────────


def test_runtime_cache_key_includes_whisper_model(monkeypatch):
    monkeypatch.setenv("VMB_WHISPER_MODEL", "base")
    base_key = RouterRuntime._cache_key(_URL, CostTier.CHEAP, None)

    monkeypatch.setenv("VMB_WHISPER_MODEL", "small")
    small_key = RouterRuntime._cache_key(_URL, CostTier.CHEAP, None)

    assert base_key != small_key, "换模型后必须不命中旧缓存"


def test_runtime_cache_key_includes_asr_chain_env(monkeypatch):
    monkeypatch.delenv("VMB_WHISPER_MODEL", raising=False)
    monkeypatch.setenv("VMB_ASR_CHAIN", "sensevoice,faster_whisper")
    a = RouterRuntime._cache_key(_URL, CostTier.CHEAP, None)

    monkeypatch.setenv("VMB_ASR_CHAIN", "faster_whisper")
    b = RouterRuntime._cache_key(_URL, CostTier.CHEAP, None)

    assert a != b, "换 ASR 链后必须不命中旧缓存"


def test_runtime_cache_key_distinguishes_cost_and_language():
    a = RouterRuntime._cache_key(_URL, CostTier.FREE, None)
    b = RouterRuntime._cache_key(_URL, CostTier.CHEAP, None)
    c = RouterRuntime._cache_key(
        _URL, CostTier.CHEAP, ExtractOptions(asr_language="en")
    )
    assert len({a, b, c}) == 3
