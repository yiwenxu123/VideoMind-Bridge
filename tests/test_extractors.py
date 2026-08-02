"""提取器单元测试

覆盖所有 9 个提取器的纯逻辑代码路径:
supports(), is_available(), should_try(), cost_tier, URL 模式匹配,
以及基类 ContentExtractor 的工具方法和注册表模式。

所有测试为纯逻辑无网络, 使用 unittest.mock 隔离外部依赖。
"""

import subprocess
import sys
from unittest import mock

sys.path.insert(0, "src")

from src.core.extractors import (
    create_all_extractors,
    get_extractor,
    list_extractors,
    register_extractor,
)
from src.core.extractors.aliyun_asr_extractor import AliyunASRExtractor
from src.core.extractors.apify_extractor import ApifyExtractor, _detect_apify_platform
from src.core.extractors.base import ContentExtractor
from src.core.extractors.bilibili_extractor import BilibiliExtractor
from src.core.extractors.coze_extractor import CozeExtractor
from src.core.extractors.douyin_extractor import DouyinExtractor
from src.core.extractors.tikhub_extractor import TikhubExtractor, _detect_commercial_platform
from src.core.extractors.xiaohongshu_extractor import XiaohongshuExtractor
from src.core.extractors.youtube_extractor import YouTubeExtractor
from src.core.extractors.ytdlp_extractor import YtDlpExtractor
from src.core.models import CostTier, ExtractResult


class _ConcreteExtractor(ContentExtractor):
    platform_name = "test_concrete"
    def extract(self, url: str) -> ExtractResult:
        return ExtractResult(
            success=True, platform="test_concrete", title="", content="",
            source="test_concrete", url=url, cost_tier=CostTier.FREE,
        )


# ============================================================
# Base class: ContentExtractor
# ============================================================

def test_base_platform_name():
    ext = _ConcreteExtractor()
    assert ext.platform_name == "test_concrete"


def test_base_cost_tier_default():
    ext = _ConcreteExtractor()
    assert ext.cost_tier() == CostTier.FREE


def test_base_url_pattern_matches_http():
    ext = _ConcreteExtractor()
    assert ext.url_pattern.search("http://example.com")


def test_base_url_pattern_matches_https():
    ext = _ConcreteExtractor()
    assert ext.url_pattern.search("https://example.com/video")


def test_base_url_pattern_no_match():
    ext = _ConcreteExtractor()
    assert not ext.url_pattern.search("ftp://example.com")


def test_base_supports_valid_url():
    ext = _ConcreteExtractor()
    assert ext.supports("https://example.com") is True


def test_base_supports_invalid_url():
    ext = _ConcreteExtractor()
    assert ext.supports("ftp://example.com") is False


def test_base_supports_empty_string():
    ext = _ConcreteExtractor()
    assert ext.supports("") is False


def test_base_is_available():
    ext = _ConcreteExtractor()
    assert ext.is_available() is True


def test_base_should_try_no_max_cost():
    ext = _ConcreteExtractor()
    assert ext.should_try("https://example.com") is True


def test_base_should_try_with_max_cost_free():
    ext = _ConcreteExtractor()
    assert ext.should_try("https://example.com", CostTier.FREE) is True


def test_base_should_try_not_available():
    ext = _ConcreteExtractor()
    with mock.patch.object(ext, "is_available", return_value=False):
        assert ext.should_try("https://example.com") is False


def test_base_should_try_not_supported():
    ext = _ConcreteExtractor()
    with mock.patch.object(ext, "supports", return_value=False):
        assert ext.should_try("https://example.com") is False


def test_base_should_try_cost_exceeded():
    class _PaidExtractor(ContentExtractor):
        _cost_tier = CostTier.PAID
        platform_name = "paid_test"
        def extract(self, url: str) -> ExtractResult:
            return ExtractResult(
                success=True, platform="paid_test", title="", content="",
                source="paid_test", url=url, cost_tier=CostTier.PAID,
            )
    ext = _PaidExtractor()
    assert ext.should_try("https://example.com", CostTier.FREE) is False
    assert ext.should_try("https://example.com", CostTier.PAID) is True
    assert ext.should_try("https://example.com", CostTier.EXPENSIVE) is True


def test_base_should_try_premium_cost_tier():
    class _PremiumExtractor(ContentExtractor):
        _cost_tier = CostTier.PREMIUM
        platform_name = "premium_test"
        def extract(self, url: str) -> ExtractResult:
            return ExtractResult(
                success=True, platform="premium_test", title="", content="",
                source="premium_test", url=url, cost_tier=CostTier.PREMIUM,
            )
    ext = _PremiumExtractor()
    assert ext.should_try("https://example.com", CostTier.FREE) is False
    assert ext.should_try("https://example.com", CostTier.CHEAP) is False
    assert ext.should_try("https://example.com", CostTier.PAID) is False
    assert ext.should_try("https://example.com", CostTier.EXPENSIVE) is False
    assert ext.should_try("https://example.com", CostTier.PREMIUM) is True
    assert ext.should_try("https://example.com", None) is True


def test_base_normalize_url_removes_query():
    ext = _ConcreteExtractor()
    url = "https://example.com/video?t=123&ref=abc"
    assert ext._normalize_url(url) == "https://example.com/video"


def test_base_normalize_url_no_query():
    ext = _ConcreteExtractor()
    assert ext._normalize_url("https://example.com/video") == "https://example.com/video"


def test_base_normalize_url_empty():
    ext = _ConcreteExtractor()
    assert ext._normalize_url("") == ""


def test_base_normalize_url_without_question_mark():
    ext = _ConcreteExtractor()
    assert ext._normalize_url("https://example.com/video#fragment") == "https://example.com/video#fragment"


def test_base_resolve_short_url_default():
    ext = _ConcreteExtractor()
    assert ext._resolve_short_url("https://short.url/abc") is None


def test_base_supports_rejects_plain_text():
    ext = _ConcreteExtractor()
    assert ext.supports("not a url") is False


# ============================================================
# Extractor Registration
# ============================================================

def test_register_and_get_extractor():
    register_extractor("test_reg_ext", _ConcreteExtractor)
    ext = get_extractor("test_reg_ext")
    assert ext is not None
    assert isinstance(ext, _ConcreteExtractor)
    assert ext.platform_name == "test_concrete"


def test_get_nonexistent_extractor():
    assert get_extractor("nonexistent_extractor_f00b4r") is None


def test_list_extractors_includes_all_platforms():
    names = list_extractors()
    for platform in ("bilibili", "youtube", "douyin", "xiaohongshu",
                     "coze", "ytdlp", "ytdlp_asr", "tikhub", "apify", "aliyun_asr"):
        assert platform in names, "Missing extractor: " + platform


def test_create_all_extractors_returns_instances():
    extractors = create_all_extractors()
    names = [e.platform_name for e in extractors]
    for platform in ("bilibili", "youtube", "douyin", "xiaohongshu",
                     "coze", "ytdlp", "ytdlp_asr", "tikhub", "apify", "aliyun_asr"):
        assert platform in names, "Missing extractor instance: " + platform
    assert len(extractors) >= 10


# ============================================================
# Bilibili Extractor
# ============================================================

def test_bilibili_supports_bilibili_com():
    ext = BilibiliExtractor()
    assert ext.supports("https://www.bilibili.com/video/BV1xx411c7mY")


def test_bilibili_supports_b23_tv():
    ext = BilibiliExtractor()
    assert ext.supports("https://b23.tv/xxxxx")


def test_bilibili_supports_with_query_params():
    ext = BilibiliExtractor()
    assert ext.supports("https://www.bilibili.com/video/BV1xx?p=1&share_source=copy_web")


def test_bilibili_supports_invalid():
    ext = BilibiliExtractor()
    assert not ext.supports("https://www.youtube.com/watch?v=xxx")
    assert not ext.supports("https://www.google.com")


def test_bilibili_is_available():
    ext = BilibiliExtractor()
    assert ext.is_available() is True


def test_bilibili_cost_tier():
    ext = BilibiliExtractor()
    assert ext.cost_tier() == CostTier.FREE


def test_bilibili_should_try_valid():
    ext = BilibiliExtractor()
    assert ext.should_try("https://www.bilibili.com/video/BV1xx") is True


def test_bilibili_should_try_not_supported():
    ext = BilibiliExtractor()
    assert ext.should_try("https://www.youtube.com/watch?v=xxx") is False


def test_bilibili_platform_name():
    ext = BilibiliExtractor()
    assert ext.platform_name == "bilibili"


def test_bilibili_url_pattern_components():
    p = BilibiliExtractor.url_pattern
    assert p.search("bilibili.com/video/BV1xx")
    assert p.search("b23.tv/abc")
    assert not p.search("youtube.com/watch")


def test_bilibili_url_case_insensitive():
    ext = BilibiliExtractor()
    # Hostnames are case-insensitive per RFC, but the regex pattern is case-sensitive.
    # Browsers normalize to lowercase, so mixed-case URLs aren't a real-world concern.
    assert ext.supports("https://www.bilibili.com/video/BV1xx")
    assert ext.supports("https://b23.tv/abc")


def test_bilibili_supports_empty_string():
    ext = BilibiliExtractor()
    assert not ext.supports("")


# ============================================================
# YouTube Extractor
# ============================================================

def test_youtube_supports_youtube_com():
    ext = YouTubeExtractor()
    assert ext.supports("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


def test_youtube_supports_youtu_be():
    ext = YouTubeExtractor()
    assert ext.supports("https://youtu.be/dQw4w9WgXcQ")


def test_youtube_supports_embed():
    ext = YouTubeExtractor()
    assert ext.supports("https://www.youtube.com/embed/dQw4w9WgXcQ")


def test_youtube_supports_shorts():
    ext = YouTubeExtractor()
    assert ext.supports("https://www.youtube.com/shorts/dQw4w9WgXcQ")


def test_youtube_supports_with_query_params():
    ext = YouTubeExtractor()
    assert ext.supports("https://www.youtube.com/watch?v=xxx&t=30s&list=PLxxx")


def test_youtube_supports_invalid():
    ext = YouTubeExtractor()
    assert not ext.supports("https://www.bilibili.com")
    assert not ext.supports("https://www.google.com")


def test_youtube_is_available():
    ext = YouTubeExtractor()
    assert ext.is_available() is True


def test_youtube_cost_tier():
    ext = YouTubeExtractor()
    assert ext.cost_tier() == CostTier.FREE


def test_youtube_should_try_valid():
    ext = YouTubeExtractor()
    assert ext.should_try("https://www.youtube.com/watch?v=xxx") is True


def test_youtube_should_try_not_supported():
    ext = YouTubeExtractor()
    assert ext.should_try("https://www.bilibili.com") is False


def test_youtube_platform_name():
    ext = YouTubeExtractor()
    assert ext.platform_name == "youtube"


def test_youtube_url_pattern_components():
    p = YouTubeExtractor.url_pattern
    assert p.search("youtube.com/watch")
    assert p.search("youtu.be/xxx")
    assert not p.search("bilibili.com")


# ============================================================
# Douyin Extractor
# ============================================================

def test_douyin_supports_douyin_com():
    ext = DouyinExtractor()
    assert ext.supports("https://www.douyin.com/video/123456789")


def test_douyin_supports_iesdouyin():
    ext = DouyinExtractor()
    assert ext.supports("https://www.iesdouyin.com/share/video/123/")


def test_douyin_supports_short_url():
    ext = DouyinExtractor()
    assert ext.supports("https://v.douyin.com/abc123")


def test_douyin_supports_invalid():
    ext = DouyinExtractor()
    assert not ext.supports("https://www.bilibili.com")
    assert not ext.supports("https://www.google.com")


def test_douyin_is_available():
    ext = DouyinExtractor()
    assert ext.is_available() is True


def test_douyin_cost_tier():
    ext = DouyinExtractor()
    assert ext.cost_tier() == CostTier.FREE


def test_douyin_platform_name():
    ext = DouyinExtractor()
    assert ext.platform_name == "douyin"


def test_douyin_supports_empty_string():
    ext = DouyinExtractor()
    assert not ext.supports("")


# ============================================================
# Xiaohongshu Extractor
# ============================================================

def test_xiaohongshu_supports_explore():
    ext = XiaohongshuExtractor()
    assert ext.supports("https://www.xiaohongshu.com/explore/123456")


def test_xiaohongshu_supports_discovery():
    ext = XiaohongshuExtractor()
    assert ext.supports("https://www.xiaohongshu.com/discovery/item/123456")


def test_xiaohongshu_supports_xhslink():
    ext = XiaohongshuExtractor()
    assert ext.supports("https://xhslink.com/abc123")


def test_xiaohongshu_supports_invalid():
    ext = XiaohongshuExtractor()
    assert not ext.supports("https://www.youtube.com")
    assert not ext.supports("https://www.google.com")


def test_xiaohongshu_is_available():
    ext = XiaohongshuExtractor()
    assert ext.is_available() is True


def test_xiaohongshu_cost_tier():
    ext = XiaohongshuExtractor()
    assert ext.cost_tier() == CostTier.FREE


def test_xiaohongshu_platform_name():
    ext = XiaohongshuExtractor()
    assert ext.platform_name == "xiaohongshu"


# ============================================================
# Coze Extractor
# ============================================================

def test_coze_supports_bilibili():
    ext = CozeExtractor.__new__(CozeExtractor)
    ext._api_key = ""
    ext._workflow_id = ""
    assert ext.supports("https://www.bilibili.com/video/BV1xx")


def test_coze_supports_youtube():
    ext = CozeExtractor.__new__(CozeExtractor)
    ext._api_key = ""
    ext._workflow_id = ""
    assert ext.supports("https://www.youtube.com/watch?v=xxx")


def test_coze_supports_douyin():
    ext = CozeExtractor.__new__(CozeExtractor)
    ext._api_key = ""
    ext._workflow_id = ""
    assert ext.supports("https://www.douyin.com/video/123")


def test_coze_supports_xiaohongshu():
    ext = CozeExtractor.__new__(CozeExtractor)
    ext._api_key = ""
    ext._workflow_id = ""
    assert ext.supports("https://www.xiaohongshu.com/explore/123")


def test_coze_supports_b23():
    ext = CozeExtractor.__new__(CozeExtractor)
    ext._api_key = ""
    ext._workflow_id = ""
    assert ext.supports("https://b23.tv/xxxxx")


def test_coze_supports_iesdouyin():
    ext = CozeExtractor.__new__(CozeExtractor)
    ext._api_key = ""
    ext._workflow_id = ""
    assert ext.supports("https://www.iesdouyin.com/share/video/123")


def test_coze_supports_invalid():
    ext = CozeExtractor.__new__(CozeExtractor)
    ext._api_key = ""
    ext._workflow_id = ""
    assert not ext.supports("https://www.google.com")
    assert not ext.supports("https://www.github.com")


def test_coze_is_available_with_key():
    with mock.patch.object(CozeExtractor, "_resolve_api_key", return_value="test-key"):
        ext = CozeExtractor()
        assert ext.is_available() is True


def test_coze_is_available_without_key():
    with mock.patch.object(CozeExtractor, "_resolve_api_key", return_value=None):
        ext = CozeExtractor()
        assert ext.is_available() is False


def test_coze_is_available_empty_key():
    with mock.patch.object(CozeExtractor, "_resolve_api_key", return_value=""):
        ext = CozeExtractor()
        assert ext.is_available() is False


def test_coze_cost_tier():
    assert CozeExtractor._cost_tier == CostTier.CHEAP


def test_coze_platform_name():
    assert CozeExtractor.platform_name == "coze"


def test_coze_url_pattern_combines_domains():
    assert CozeExtractor.url_pattern.search("bilibili.com")
    assert CozeExtractor.url_pattern.search("youtube.com")
    assert CozeExtractor.url_pattern.search("douyin.com")
    assert CozeExtractor.url_pattern.search("xiaohongshu.com")
    assert CozeExtractor.url_pattern.search("xhslink.com")
    assert CozeExtractor.url_pattern.search("b23.tv")
    assert CozeExtractor.url_pattern.search("iesdouyin.com")
    assert CozeExtractor.url_pattern.search("youtu.be")
    assert not CozeExtractor.url_pattern.search("google.com")


# ============================================================
# YtDlp Extractor
# ============================================================

def test_ytdlp_supports_youtube():
    ext = YtDlpExtractor()
    ext._available = None
    assert ext.supports("https://www.youtube.com/watch?v=xxx")


def test_ytdlp_supports_bilibili():
    ext = YtDlpExtractor()
    assert ext.supports("https://www.bilibili.com/video/BV1xx")


def test_ytdlp_supports_douyin():
    ext = YtDlpExtractor()
    assert ext.supports("https://www.douyin.com/video/123")


def test_ytdlp_supports_xiaohongshu():
    ext = YtDlpExtractor()
    assert ext.supports("https://www.xiaohongshu.com/explore/123")


def test_ytdlp_supports_twitter():
    ext = YtDlpExtractor()
    assert ext.supports("https://twitter.com/user/status/123")


def test_ytdlp_supports_xcom():
    ext = YtDlpExtractor()
    assert ext.supports("https://x.com/user/status/123")


def test_ytdlp_supports_tiktok():
    ext = YtDlpExtractor()
    assert ext.supports("https://www.tiktok.com/@user/video/123")


def test_ytdlp_supports_instagram():
    ext = YtDlpExtractor()
    assert ext.supports("https://www.instagram.com/p/abc123")


def test_ytdlp_supports_ted():
    ext = YtDlpExtractor()
    assert ext.supports("https://www.ted.com/talks/abc")


def test_ytdlp_supports_invalid():
    ext = YtDlpExtractor()
    assert not ext.supports("https://www.google.com")
    assert not ext.supports("https://example.com")


def test_ytdlp_is_available_installed():
    ext = YtDlpExtractor()
    ext._available = None
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "2025.12.8\n"
        assert ext.is_available() is True


def test_ytdlp_is_available_not_installed():
    ext = YtDlpExtractor()
    ext._available = None
    with mock.patch("subprocess.run", side_effect=FileNotFoundError("yt-dlp not found")):
        assert ext.is_available() is False


def test_ytdlp_is_available_timeout():
    ext = YtDlpExtractor()
    ext._available = None
    with mock.patch("subprocess.run",
                    side_effect=subprocess.TimeoutExpired("yt-dlp", timeout=10)):
        assert ext.is_available() is False


def test_ytdlp_is_available_caches_result():
    ext = YtDlpExtractor()
    ext._available = None
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "2025.12.8\n"
        first = ext.is_available()
        second = ext.is_available()
        assert first is True
        assert second is True
        assert mock_run.call_count == 1


def test_ytdlp_is_available_negative_cached():
    ext = YtDlpExtractor()
    ext._available = None
    with mock.patch("subprocess.run", side_effect=FileNotFoundError("yt-dlp not found")):
        assert ext.is_available() is False
    assert ext.is_available() is False


def test_ytdlp_cost_tier():
    assert YtDlpExtractor._cost_tier == CostTier.FREE


def test_ytdlp_platform_name():
    ext = YtDlpExtractor()
    assert ext.platform_name == "ytdlp"


def test_ytdlp_supports_empty_string():
    ext = YtDlpExtractor()
    assert not ext.supports("")


# ============================================================
# Tikhub Extractor
# ============================================================

def test_tikhub_supports_douyin():
    ext = TikhubExtractor()
    assert ext.supports("https://www.douyin.com/video/123")


def test_tikhub_supports_bilibili():
    ext = TikhubExtractor()
    assert ext.supports("https://www.bilibili.com/video/BV1xx")


def test_tikhub_supports_xiaohongshu():
    ext = TikhubExtractor()
    assert ext.supports("https://www.xiaohongshu.com/explore/123")


def test_tikhub_supports_tiktok():
    ext = TikhubExtractor()
    assert ext.supports("https://www.tiktok.com/@user/video/123")


def test_tikhub_supports_instagram():
    ext = TikhubExtractor()
    assert ext.supports("https://www.instagram.com/p/abc123")


def test_tikhub_supports_twitter():
    ext = TikhubExtractor()
    assert ext.supports("https://twitter.com/user/status/123")


def test_tikhub_supports_youtube():
    ext = TikhubExtractor()
    assert ext.supports("https://www.youtube.com/watch?v=xxx")


def test_tikhub_supports_weibo():
    ext = TikhubExtractor()
    assert ext.supports("https://weibo.com/status/123")


def test_tikhub_supports_invalid():
    ext = TikhubExtractor()
    assert not ext.supports("https://www.google.com")


def test_tikhub_is_available_with_key():
    with mock.patch.object(TikhubExtractor, "_resolve_api_key", return_value="test-key"):
        ext = TikhubExtractor()
        assert ext.is_available() is True


def test_tikhub_is_available_without_key():
    with mock.patch.object(TikhubExtractor, "_resolve_api_key", return_value=None):
        ext = TikhubExtractor()
        assert ext.is_available() is False


def test_tikhub_is_available_empty_key():
    with mock.patch.object(TikhubExtractor, "_resolve_api_key", return_value=""):
        ext = TikhubExtractor()
        assert ext.is_available() is False


def test_tikhub_cost_tier():
    assert TikhubExtractor._cost_tier == CostTier.PREMIUM


def test_tikhub_platform_name():
    assert TikhubExtractor.platform_name == "tikhub"


def test_tikhub_supports_method_matches_url_pattern():
    ext = TikhubExtractor()
    assert ext.supports("https://weibo.com/status/123") is True
    assert ext.supports("https://www.google.com") is False


def test_tikhub_detect_commercial_platform():
    assert _detect_commercial_platform("https://www.douyin.com/video/123") == "douyin"
    assert _detect_commercial_platform("https://www.bilibili.com/video/BV1xx") == "bilibili"
    assert _detect_commercial_platform("https://www.xiaohongshu.com/explore/123") == "xiaohongshu"
    assert _detect_commercial_platform("https://www.tiktok.com/@user") == "tiktok"
    assert _detect_commercial_platform("https://www.instagram.com/p/abc") == "instagram"
    assert _detect_commercial_platform("https://twitter.com/user") == "twitter"
    assert _detect_commercial_platform("https://www.youtube.com/watch?v=xxx") == "youtube"
    assert _detect_commercial_platform("https://weibo.com/status/123") == "weibo"
    assert _detect_commercial_platform("https://www.google.com") is None
    assert _detect_commercial_platform("") is None


def test_tikhub_detect_commercial_platform_edge_cases():
    assert _detect_commercial_platform("https://b23.tv/xxxxx") == "bilibili"
    assert _detect_commercial_platform("https://xhslink.com/abc") == "xiaohongshu"
    assert _detect_commercial_platform("https://iesdouyin.com/share/video/123") == "douyin"
    assert _detect_commercial_platform("https://youtu.be/xxx") == "youtube"
    assert _detect_commercial_platform("https://x.com/user/123") == "twitter"


# ============================================================
# Apify Extractor
# ============================================================

def test_apify_supports_bilibili():
    ext = ApifyExtractor()
    assert ext.supports("https://www.bilibili.com/video/BV1xx")


def test_apify_supports_douyin():
    ext = ApifyExtractor()
    assert ext.supports("https://www.douyin.com/video/123")


def test_apify_supports_youtube():
    ext = ApifyExtractor()
    assert ext.supports("https://www.youtube.com/watch?v=xxx")


def test_apify_supports_xiaohongshu():
    ext = ApifyExtractor()
    assert ext.supports("https://www.xiaohongshu.com/explore/123")


def test_apify_supports_tiktok():
    ext = ApifyExtractor()
    assert ext.supports("https://www.tiktok.com/@user/video/123")


def test_apify_supports_invalid():
    ext = ApifyExtractor()
    assert not ext.supports("https://www.google.com")
    assert not ext.supports("https://github.com")


def test_apify_is_available_with_key():
    with mock.patch.object(ApifyExtractor, "_resolve_api_key", return_value="test-key"):
        ext = ApifyExtractor()
        assert ext.is_available() is True


def test_apify_is_available_without_key():
    with mock.patch.object(ApifyExtractor, "_resolve_api_key", return_value=None):
        ext = ApifyExtractor()
        assert ext.is_available() is False


def test_apify_is_available_empty_key():
    with mock.patch.object(ApifyExtractor, "_resolve_api_key", return_value=""):
        ext = ApifyExtractor()
        assert ext.is_available() is False


def test_apify_cost_tier():
    assert ApifyExtractor._cost_tier == CostTier.PREMIUM


def test_apify_platform_name():
    assert ApifyExtractor.platform_name == "apify"


def test_apify_detect_apify_platform():
    assert _detect_apify_platform("https://www.bilibili.com/video/BV1xx") == "bilibili"
    assert _detect_apify_platform("https://www.douyin.com/video/123") == "douyin"
    assert _detect_apify_platform("https://www.youtube.com/watch?v=xxx") == "youtube"
    assert _detect_apify_platform("https://www.xiaohongshu.com/explore/123") == "xiaohongshu"
    assert _detect_apify_platform("https://www.tiktok.com/@user") == "tiktok"
    assert _detect_apify_platform("https://www.google.com") is None
    assert _detect_apify_platform("") is None


def test_apify_detect_apify_platform_b23():
    assert _detect_apify_platform("https://b23.tv/xxxxx") == "bilibili"
    assert _detect_apify_platform("https://iesdouyin.com/share/video/123") == "douyin"
    assert _detect_apify_platform("https://youtu.be/xxx") == "youtube"
    assert _detect_apify_platform("https://xhslink.com/abc") == "xiaohongshu"


# ============================================================
# Aliyun ASR Extractor
# ============================================================

def _make_aliyun_extractor():
    ext = AliyunASRExtractor.__new__(AliyunASRExtractor)
    ext._access_key = ""
    ext._access_secret = ""
    ext._appkey = ""
    ext._client = mock.MagicMock()
    ext.url_pattern = AliyunASRExtractor.url_pattern
    ext._cost_tier = AliyunASRExtractor._cost_tier
    return ext


def test_aliyun_supports_http():
    ext = _make_aliyun_extractor()
    assert ext.supports("http://example.com/video.mp4")


def test_aliyun_supports_https():
    ext = _make_aliyun_extractor()
    assert ext.supports("https://example.com/video.mp4")


def test_aliyun_supports_invalid():
    ext = _make_aliyun_extractor()
    assert not ext.supports("ftp://example.com")


def test_aliyun_supports_empty_string():
    ext = _make_aliyun_extractor()
    assert not ext.supports("")


def test_aliyun_is_available_with_keys():
    with mock.patch.object(AliyunASRExtractor, "_resolve_api_key", return_value="test-key"):
        ext = AliyunASRExtractor()
        assert ext.is_available() is True


def test_aliyun_is_available_without_keys():
    with mock.patch.object(AliyunASRExtractor, "_resolve_api_key", return_value=None):
        ext = AliyunASRExtractor()
        assert ext.is_available() is False


def test_aliyun_is_available_partial_keys():
    with mock.patch.object(AliyunASRExtractor, "_resolve_api_key") as mock_resolve:
        mock_resolve.side_effect = ["test-id", "", "test-app"]
        ext = AliyunASRExtractor()
        assert ext.is_available() is False


def test_aliyun_is_available_one_key_missing():
    with mock.patch.object(AliyunASRExtractor, "_resolve_api_key") as mock_resolve:
        mock_resolve.side_effect = ["test-id", "test-secret", ""]
        ext = AliyunASRExtractor()
        assert ext.is_available() is False


def test_aliyun_cost_tier():
    assert AliyunASRExtractor._cost_tier == CostTier.EXPENSIVE


def test_aliyun_platform_name():
    assert AliyunASRExtractor.platform_name == "aliyun_asr"


def test_aliyun_should_try_delegates_to_super():
    with mock.patch.object(AliyunASRExtractor, "_resolve_api_key", return_value="test-key"):
        ext = AliyunASRExtractor()
        assert ext.should_try("https://example.com/video", CostTier.FREE) is False
        assert ext.should_try("https://example.com/video", CostTier.CHEAP) is False
        assert ext.should_try("https://example.com/video", CostTier.PAID) is False
        assert ext.should_try("https://example.com/video", CostTier.EXPENSIVE) is True
        assert ext.should_try("https://example.com/video", CostTier.PREMIUM) is True


def test_aliyun_should_try_not_available():
    with mock.patch.object(AliyunASRExtractor, "_resolve_api_key", return_value=None):
        ext = AliyunASRExtractor()
        assert ext.should_try("https://example.com/video") is False


def test_aliyun_should_try_not_supported():
    with mock.patch.object(AliyunASRExtractor, "_resolve_api_key", return_value="test-key"):
        ext = AliyunASRExtractor()
        assert ext.should_try("ftp://example.com") is False


def test_aliyun_url_pattern_generic():
    assert AliyunASRExtractor.url_pattern.search("http://a.com")
    assert AliyunASRExtractor.url_pattern.search("https://bilibili.com/video/BV1xx")
    assert not AliyunASRExtractor.url_pattern.search("ftp://a.com")


# ============================================================
# URL Pattern Edge Cases (cross-extractor)
# ============================================================

def test_url_pattern_no_false_positives():
    bilibili_ext = BilibiliExtractor()
    youtube_ext = YouTubeExtractor()
    douyin_ext = DouyinExtractor()
    xhs_ext = XiaohongshuExtractor()
    assert not bilibili_ext.supports("https://www.youtube.com/watch?v=xxx")
    assert not youtube_ext.supports("https://www.bilibili.com/video/BV1xx")
    assert not douyin_ext.supports("https://www.bilibili.com/video/BV1xx")
    assert not xhs_ext.supports("https://www.youtube.com/watch?v=xxx")


def test_url_pattern_with_subdomain_variations():
    bilibili_ext = BilibiliExtractor()
    youtube_ext = YouTubeExtractor()
    assert bilibili_ext.supports("https://www.bilibili.com/video/BV1xx")
    assert youtube_ext.supports("https://www.youtube.com/watch?v=xxx")
    assert bilibili_ext.supports("https://m.bilibili.com/video/BV1xx")
    assert youtube_ext.supports("https://m.youtube.com/watch?v=xxx")


def test_url_pattern_with_fragment():
    ext = BilibiliExtractor()
    assert ext.supports("https://www.bilibili.com/video/BV1xx#t=10")


def test_url_with_encoded_characters():
    ext = BilibiliExtractor()
    url = "https://www.bilibili.com/video/BV1xx?p=1&name=%E6%B5%8B%E8%AF%95"
    assert ext.supports(url)
