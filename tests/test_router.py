"""ContentRouter 测试"""
from unittest import mock

import pytest

from src.core.models import CostTier, ExtractResult
from src.core.router import ContentRouter, RouterConfig


@pytest.fixture
def mock_extractors():
    """创建模拟提取器环境"""
    with mock.patch("src.core.router.create_all_extractors") as mock_create:
        # 创建两个模拟提取器
        mock_free = mock.Mock()
        mock_free.platform_name = "mock_free"
        mock_free.is_available.return_value = True
        mock_free.supports.return_value = True
        mock_free.cost_tier.return_value = CostTier.FREE
        mock_free.extract.return_value = ExtractResult(
            success=True, platform="free", title="Free Video",
            content="free content", source="mock_free",
            url="https://example.com/free", cost_tier=CostTier.FREE,
        )

        mock_cheap = mock.Mock()
        mock_cheap.platform_name = "mock_cheap"
        mock_cheap.is_available.return_value = True
        mock_cheap.supports.return_value = True
        mock_cheap.cost_tier.return_value = CostTier.CHEAP
        mock_cheap.extract.return_value = ExtractResult(
            success=True, platform="cheap", title="Cheap Video",
            content="cheap content", source="mock_cheap",
            url="https://example.com/cheap", cost_tier=CostTier.CHEAP,
        )

        mock_create.return_value = [mock_free, mock_cheap]
        yield mock_free, mock_cheap


def test_extract_uses_cache(mock_extractors):
    """缓存命中时直接返回缓存结果"""
    cached_result = ExtractResult(
        success=True, platform="free", title="Cached",
        content="cached", source="mock_free",
        url="https://example.com/cached", cost_tier=CostTier.FREE,
    )
    router = ContentRouter(RouterConfig(cache={"https://example.com/cached": cached_result}))
    result = router.extract("https://example.com/cached")
    assert result.title == "Cached"


def test_extract_skips_cache_when_cost_exceeded(mock_extractors):
    """缓存命中但成本超限时跳过缓存"""
    cached_result = ExtractResult(
        success=True, platform="cheap", title="Expensive Cache",
        content="cached", source="mock_cheap", cost_tier=CostTier.CHEAP,
        url="https://example.com/cached",
    )
    router = ContentRouter(RouterConfig(
        priority=["mock_free", "mock_cheap"],
        cache={"https://example.com/cached": cached_result},
    ))
    result = router.extract("https://example.com/cached", max_cost=CostTier.FREE)
    # 缓存被跳过（FREE < CHEAP），应使用 FREE 提取器
    assert result.source == "mock_free"


def test_extract_skips_unknown_extractor_in_priority():
    """优先级中引用不存在的提取器时跳过（不崩溃）"""
    with mock.patch("src.core.router.create_all_extractors", return_value=[]):
        router = ContentRouter(RouterConfig(priority=["nonexistent", "bilibili"]))
    # 覆盖到 line 102: continue for None extractor
    with mock.patch.object(router, "_extractors", {}):
        result = router.extract("https://example.com/test")
        assert result.success is False


def test_extract_cost_tier_filtering(mock_extractors):
    """max_cost 过滤高成本提取器"""
    mock_free, mock_cheap = mock_extractors
    # 设置 mock_free 不支持当前 URL → 跳过 → 无可用提取器
    mock_free.supports.return_value = False
    mock_cheap.supports.return_value = True

    router = ContentRouter(RouterConfig(priority=["mock_free", "mock_cheap"]))
    result = router.extract("https://example.com/test", max_cost=CostTier.FREE)
    # mock_cheap CostTier.CHEAP > FREE，应被过滤
    assert result.success is False
    assert mock_cheap.extract.called is False


def test_extract_cost_tier_filtering_config_level(mock_extractors):
    """config.max_cost_tier 过滤高成本提取器"""
    mock_free, mock_cheap = mock_extractors
    mock_free.supports.return_value = False
    mock_cheap.supports.return_value = True

    router = ContentRouter(RouterConfig(max_cost_tier=CostTier.FREE, priority=["mock_free", "mock_cheap"]))
    result = router.extract("https://example.com/test")
    # mock_cheap CostTier.CHEAP > FREE，应被过滤
    assert result.success is False
    assert mock_cheap.extract.called is False


def test_extract_all_fail_with_last_result(mock_extractors):
    """所有提取器失败，但有 last_result 时返回修改后的失败结果 (lines 145-146)"""
    mock_free, mock_cheap = mock_extractors
    mock_free.extract.return_value = ExtractResult(
        success=False, platform="free", title="Free",
        content="", source="mock_free", url="https://example.com/fail",
        cost_tier=CostTier.FREE, error="rate limit",
    )
    mock_cheap.extract.return_value = ExtractResult(
        success=False, platform="cheap", title="Cheap",
        content="", source="mock_cheap", url="https://example.com/fail",
        cost_tier=CostTier.CHEAP, error="timeout",
    )

    router = ContentRouter(RouterConfig(priority=["mock_free", "mock_cheap"]))
    result = router.extract("https://example.com/fail")
    assert result.success is False
    assert "rate limit" in result.error
    assert "timeout" in result.error


def test_extract_all_fail_with_exception(mock_extractors):
    """提取器抛出异常时被捕获 (line 137-140)"""
    mock_free, mock_cheap = mock_extractors
    mock_free.extract.side_effect = RuntimeError("network down")
    mock_cheap.extract.side_effect = ValueError("bad response")

    router = ContentRouter(RouterConfig(priority=["mock_free", "mock_cheap"]))
    result = router.extract("https://example.com/error")
    assert result.success is False
    assert str(result.error) is not None
    assert "network down" in str(result.error)
    assert "bad response" in str(result.error)


def test_extract_no_supporting_extractor():
    """没有提取器支持该 URL 时返回正确错误"""
    with mock.patch("src.core.router.create_all_extractors") as mock_create:
        mock_ext = mock.Mock()
        mock_ext.platform_name = "mock_only"
        mock_ext.is_available.return_value = True
        mock_ext.supports.return_value = False  # 不支持任何 URL
        mock_create.return_value = [mock_ext]

        router = ContentRouter(RouterConfig(priority=["mock_only"]))
        result = router.extract("https://example.com/unsupported")
        assert result.success is False
        assert "无可用提取器" in result.error or "不支持" in result.error


def test_list_extractors(mock_extractors):
    """列出提取器状态"""
    router = ContentRouter(RouterConfig(priority=["mock_free", "mock_cheap"]))
    ext_list = router.list_extractors()
    assert "mock_free" in ext_list
    assert ext_list["mock_free"] is True


def test_extract_skips_unavailable_extractor(mock_extractors):
    """提取器不可用时跳过 (line 108-109)"""
    mock_free, mock_cheap = mock_extractors
    mock_free.is_available.return_value = False
    mock_cheap.supports.return_value = False

    router = ContentRouter(RouterConfig(priority=["mock_free", "mock_cheap", "bilibili"]))
    result = router.extract("https://example.com/test")
    assert result.success is False


def test_get_extractor(mock_extractors):
    """获取单个提取器"""
    router = ContentRouter(RouterConfig(priority=["mock_free", "mock_cheap"]))
    ext = router.get_extractor("mock_free")
    assert ext is not None
    ext2 = router.get_extractor("nonexistent")
    assert ext2 is None


def test_router_preserves_best_metadata_on_total_failure(mock_extractors):
    """全部提取器失败时, 应保留沿途最佳标题/平台/时长"""
    from src.core.router import ContentRouter, RouterConfig

    free_ext, cheap_ext = mock_extractors

    def fail_with_title(url):
        return ExtractResult(
            success=False, platform="bilibili", title="有标题的视频",
            content="", source="mock_free", url=url, cost_tier=CostTier.FREE,
            duration_seconds=120.0, error="无字幕",
        )
    free_ext.extract.side_effect = fail_with_title

    def fail_no_title(url):
        return ExtractResult(
            success=False, platform="ytdlp_asr", title="", content="",
            source="mock_cheap", url=url, cost_tier=CostTier.CHEAP, error="下载失败",
        )
    cheap_ext.extract.side_effect = fail_no_title

    router = ContentRouter(RouterConfig(priority=["mock_free", "mock_cheap"]))
    result = router.extract("https://example.com/video")
    assert result.success is False
    assert result.title == "有标题的视频"
    assert result.duration_seconds == 120.0
    assert "无字幕" in result.error
    assert "下载失败" in result.error
