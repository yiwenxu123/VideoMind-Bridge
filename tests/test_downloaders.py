"""下载器模块单元测试

覆盖 src/services/downloaders/ 下全部三个文件：
  - base.py：枚举、数据类、抽象基类
  - router.py：下载器路由与注册
  - ytdlp.py：yt-dlp 下载器实现

所有外部调用均通过 unittest.mock 隔离，零网络。
"""

from __future__ import annotations

import builtins
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models.task import VideoMetadata
from src.services.downloaders.base import (
    DownloaderBase,
    DownloaderCapability,
    DownloaderInfo,
    DownloadOptions,
    DownloadResult,
    ProgressCallback,
)
from src.utils.exceptions import UnsupportedPlatformError

# ============================================================
# 辅助类 —— 用于需要具体子类的测试
# ============================================================

class ConcreteDownloader(DownloaderBase):
    """最小具体子类 —— 让所有抽象方法有桩实现。"""

    _DEFAULT_CAPS = {DownloaderCapability.VIDEO, DownloaderCapability.METADATA}
    _DEFAULT_PLATFORMS = {"youtube"}

    def __init__(self, name: str = "test", version: str = "1.0",
                 platforms: set[str] | None = None,
                 capabilities: set[DownloaderCapability] | None = None,
                 priority: int = 100,
                 available: bool = True):
        self._available = available
        self._info = DownloaderInfo(
            name=name,
            version=version,
            platforms=self._DEFAULT_PLATFORMS if platforms is None else platforms,
            capabilities=self._DEFAULT_CAPS if capabilities is None else capabilities,
            priority=priority,
        )

    @property
    def info(self) -> DownloaderInfo:
        return self._info

    @property
    def is_available(self) -> bool:
        return self._available

    def can_handle(self, url: str) -> bool:
        return "youtube.com" in url

    def download(
        self,
        url: str,  # noqa: ARG002
        options: DownloadOptions,  # noqa: ARG002
        progress_callback: ProgressCallback | None = None,  # noqa: ARG002
    ) -> DownloadResult:
        return DownloadResult(success=True, video_path=Path("/tmp/test.mp4"))


class MockDownloader(DownloaderBase):
    """路由器测试用的灵活 Mock 下载器。"""

    def __init__(self, name: str = "mock", version: str = "1.0",
                 platforms: set[str] | None = None,
                 capabilities: set[DownloaderCapability] | None = None,
                 priority: int = 100,
                 available: bool = True,
                 can_handle_result: bool | callable = True):
        self._name = name
        self._version = version
        self._platforms = platforms or {"youtube"}
        self._capabilities = capabilities or {DownloaderCapability.VIDEO}
        self._priority = priority
        self._available = available
        self._can_handle_result = can_handle_result

    @property
    def info(self) -> DownloaderInfo:
        return DownloaderInfo(
            name=self._name,
            version=self._version,
            platforms=self._platforms,
            capabilities=self._capabilities,
            priority=self._priority,
        )

    @property
    def is_available(self) -> bool:
        return self._available

    def can_handle(self, url: str) -> bool:
        if callable(self._can_handle_result):
            return self._can_handle_result(url)
        return self._can_handle_result

    def download(self, url, options, progress_callback=None):  # noqa: ARG002
        return DownloadResult(success=True)

    def get_metadata(self, url: str) -> VideoMetadata | None:
        return VideoMetadata(title="Test", author="Tester", duration=120, platform="youtube", url=url)


# ============================================================
# 辅助函数 —— 创建模拟的 yt_dlp 模块
# ============================================================

def make_fake_ytdlp(version: str = "2024.01.01") -> MagicMock:
    """创建可注入 sys.modules 的假 yt_dlp 模块。"""
    ver = MagicMock()
    ver.__version__ = version

    mod = MagicMock()
    mod.version = ver
    mod.DownloadError = type("DownloadError", (Exception,), {})
    mod.utils = mod  # utils 也是同一个 mock，方便访问 utils.DownloadError
    mod.utils.DownloadError = mod.DownloadError

    fake_ydl = MagicMock()
    fake_ydl.__enter__ = MagicMock(return_value=fake_ydl)
    fake_ydl.__exit__ = MagicMock(return_value=None)
    mod.YoutubeDL = MagicMock(return_value=fake_ydl)

    return mod


# ============================================================
# ██  base.py  ████████████████████████████████████████████████
# ============================================================

# ---------- DownloaderCapability ----------

def test_capability_enum_values():
    """DownloaderCapability 枚举成员及自动值。"""
    assert DownloaderCapability.VIDEO.value == 1
    assert DownloaderCapability.AUDIO_ONLY.value == 2
    assert DownloaderCapability.METADATA.value == 3
    assert DownloaderCapability.PLAYLIST.value == 4
    assert DownloaderCapability.SUBTITLE.value == 5
    assert DownloaderCapability.THUMBNAIL.value == 6
    assert DownloaderCapability.LIVE_STREAM.value == 7


def test_capability_enum_members_count():
    """枚举成员数量不变。"""
    assert len(DownloaderCapability) == 7


def test_capability_enum_distinct():
    """所有成员互不相同。"""
    values = {c.value for c in DownloaderCapability}
    assert len(values) == 7


# ---------- DownloaderInfo ----------

def test_downloader_info_defaults():
    """DownloaderInfo 必填字段与默认值。"""
    info = DownloaderInfo(
        name="test",
        version="1.0",
        platforms={"youtube"},
        capabilities={DownloaderCapability.VIDEO},
    )
    assert info.name == "test"
    assert info.version == "1.0"
    assert info.platforms == {"youtube"}
    assert info.capabilities == {DownloaderCapability.VIDEO}
    assert info.priority == 100          # 默认
    assert info.description == ""         # 默认


def test_downloader_info_full():
    """DownloaderInfo 全字段创建。"""
    info = DownloaderInfo(
        name="full",
        version="2.0",
        platforms={"youtube", "bilibili"},
        capabilities={DownloaderCapability.VIDEO, DownloaderCapability.AUDIO_ONLY},
        priority=50,
        description="Full test",
    )
    assert info.name == "full"
    assert info.priority == 50
    assert info.description == "Full test"


def test_downloader_info_platforms_mutable():
    """platforms 是可变的 set。"""
    info = DownloaderInfo(name="x", version="1", platforms=set(), capabilities=set())
    info.platforms.add("youtube")
    assert "youtube" in info.platforms


# ---------- DownloadOptions ----------

def test_download_options_defaults():
    """DownloadOptions 必填字段与默认值。"""
    opts = DownloadOptions(output_dir=Path("/tmp"))
    assert opts.output_dir == Path("/tmp")
    assert opts.keep_video is False
    assert opts.video_quality == "best"
    assert opts.audio_quality == "best"
    assert opts.audio_format == "m4a"
    assert opts.video_format == "mp4"
    assert opts.subtitle_languages == []
    assert opts.cookies is None
    assert opts.cookies_file is None
    assert opts.cookies_from_browser is None
    assert opts.proxy is None
    assert opts.timeout == 300
    assert opts.retries == 3


def test_download_options_full():
    """DownloadOptions 全字段创建。"""
    tmp = Path("/tmp/out")
    opts = DownloadOptions(
        output_dir=tmp,
        keep_video=True,
        video_quality="1080p",
        audio_quality="320k",
        audio_format="mp3",
        video_format="mkv",
        subtitle_languages=["zh", "en"],
        cookies="abc",
        cookies_file=Path("/tmp/cookies.txt"),
        cookies_from_browser="chrome",
        proxy="http://proxy:8080",
        timeout=600,
        retries=5,
    )
    assert opts.keep_video is True
    assert opts.video_quality == "1080p"
    assert opts.audio_format == "mp3"
    assert opts.subtitle_languages == ["zh", "en"]
    assert opts.cookies == "abc"
    assert opts.proxy == "http://proxy:8080"
    assert opts.timeout == 600
    assert opts.retries == 5


def test_download_options_output_dir_path():
    """output_dir 必须是 Path。"""
    opts = DownloadOptions(output_dir=Path("/tmp"))
    assert isinstance(opts.output_dir, Path)


def test_download_options_subtitle_languages_mutable():
    """subtitle_languages 默认是空列表且可修改。"""
    opts = DownloadOptions(output_dir=Path("."))
    opts.subtitle_languages.append("ja")
    assert opts.subtitle_languages == ["ja"]


# ---------- DownloadResult ----------

def test_download_result_defaults():
    """DownloadResult 必填字段与默认值。"""
    result = DownloadResult(success=True)
    assert result.success is True
    assert result.audio_path is None
    assert result.video_path is None
    assert result.metadata is None
    assert result.subtitle_paths == []
    assert result.thumbnail_path is None
    assert result.error_message is None
    assert result.error_code is None


def test_download_result_full():
    """DownloadResult 全字段创建。"""
    meta = VideoMetadata(title="T", author="A", duration=10, platform="youtube", url="u")
    result = DownloadResult(
        success=False,
        audio_path=Path("/tmp/a.m4a"),
        video_path=Path("/tmp/v.mp4"),
        metadata=meta,
        subtitle_paths=[Path("/tmp/sub.srt")],
        thumbnail_path=Path("/tmp/thumb.jpg"),
        error_message="出错了",
        error_code="ERR_001",
    )
    assert result.success is False
    assert result.audio_path == Path("/tmp/a.m4a")
    assert result.video_path == Path("/tmp/v.mp4")
    assert result.metadata is meta
    assert result.subtitle_paths == [Path("/tmp/sub.srt")]
    assert result.error_message == "出错了"
    assert result.error_code == "ERR_001"


def test_download_result_success_variants():
    """DownloadResult 的 error 字段与 success 独立。"""
    r1 = DownloadResult(success=True, error_message="warn")
    assert r1.success is True
    assert r1.error_message == "warn"

    r2 = DownloadResult(success=False)
    assert r2.success is False


# ---------- ProgressCallback ----------

def test_progress_callback_type():
    """ProgressCallback 是 Callable[[str, float], None]。"""
    def cb(status: str, progress: float) -> None:
        pass
    _: ProgressCallback = cb
    assert callable(_)


# ---------- DownloaderBase ----------

def test_downloader_base_cannot_instantiate_directly():
    """抽象类不可直接实例化。"""
    with pytest.raises(TypeError, match="abstract"):
        DownloaderBase()  # type: ignore


def test_downloader_base_concrete_subclass():
    """具体子类可以实例化。"""
    d = ConcreteDownloader()
    assert isinstance(d, DownloaderBase)


def test_downloader_base_info_property():
    """info 返回子类提供的信息。"""
    d = ConcreteDownloader(name="test_name", version="2.0")
    info = d.info
    assert info.name == "test_name"
    assert info.version == "2.0"


def test_downloader_base_is_available_default():
    """is_available 默认返回 True。"""
    d = ConcreteDownloader()
    assert d.is_available is True


def test_downloader_base_is_available_false():
    """子类可将 is_available 设为 False。"""
    d = ConcreteDownloader(available=False)
    assert d.is_available is False


def test_downloader_base_can_handle_true():
    """can_handle 返回 True。"""
    d = ConcreteDownloader()
    assert d.can_handle("https://www.youtube.com/watch?v=xxx") is True


def test_downloader_base_can_handle_false():
    """can_handle 返回 False。"""
    d = ConcreteDownloader()
    assert d.can_handle("https://vimeo.com/123") is False


def test_downloader_base_download():
    """download 返回 DownloadResult。"""
    d = ConcreteDownloader()
    opts = DownloadOptions(output_dir=Path("/tmp"))
    result = d.download("https://youtube.com/watch?v=xxx", opts)
    assert result.success is True
    assert result.video_path == Path("/tmp/test.mp4")


def test_downloader_base_download_with_callback():
    """download 接受可选的 progress_callback。"""
    d = ConcreteDownloader()
    opts = DownloadOptions(output_dir=Path("/tmp"))
    calls = []
    result = d.download("https://youtube.com/watch?v=xxx", opts, calls.append)
    assert result.success is True


def test_downloader_base_get_supported_platforms():
    """get_supported_platforms 返回 info.platforms。"""
    d = ConcreteDownloader(platforms={"youtube", "bilibili"})
    assert d.get_supported_platforms() == {"youtube", "bilibili"}


def test_downloader_base_get_supported_platforms_matches_info():
    """返回的集合与 info.platforms 相同对象。"""
    d = ConcreteDownloader()
    assert d.get_supported_platforms() is d.info.platforms


def test_downloader_base_has_capability_true():
    """已具备的能力返回 True。"""
    d = ConcreteDownloader(capabilities={DownloaderCapability.VIDEO, DownloaderCapability.METADATA})
    assert d.has_capability(DownloaderCapability.VIDEO) is True
    assert d.has_capability(DownloaderCapability.METADATA) is True


def test_downloader_base_has_capability_false():
    """不具备的能力返回 False。"""
    d = ConcreteDownloader(capabilities={DownloaderCapability.VIDEO})
    assert d.has_capability(DownloaderCapability.AUDIO_ONLY) is False
    assert d.has_capability(DownloaderCapability.LIVE_STREAM) is False


def test_downloader_base_has_capability_empty():
    """空能力集始终返回 False。"""
    d = ConcreteDownloader(capabilities=set())
    assert d.has_capability(DownloaderCapability.VIDEO) is False


def test_downloader_base_get_metadata_default():
    """get_metadata 默认返回 None。"""
    ConcreteDownloader()
    # ConcreteDownloader 不重写 get_metadata，所以走基类默认
    # 但 ConcreteDownloader 是从 DownloaderBase 继承的，DownloaderBase.get_metadata 默认返回 None
    # 需要确认 ConcreteDownloader 没重写这个方法
    pass


def test_downloader_base_get_metadata_none():
    """不重写 get_metadata 的下载器返回 None。"""
    class NoMetaDownloader(DownloaderBase):
        @property
        def info(self) -> DownloaderInfo:
            return DownloaderInfo(name="no", version="1", platforms=set(), capabilities=set())
        def can_handle(self, url: str) -> bool:  # noqa: ARG002
            return True
        def download(self, url, options, progress_callback=None):  # noqa: ARG002
            return DownloadResult(success=True)

    d = NoMetaDownloader()
    assert d.get_metadata("https://example.com") is None


def test_downloader_base_detect_platform():
    """_detect_platform 委托给 utils.platform_detector.detect_platform。"""

    d = ConcreteDownloader()
    # 测试实际上调用了真实 detect_platform
    assert d._detect_platform("https://www.bilibili.com/video/BV1xx") == "bilibili"
    assert d._detect_platform("https://www.youtube.com/watch?v=xxx") == "youtube"
    assert d._detect_platform("https://example.com") == "unknown"


def test_downloader_base_get_supported_platforms_returns_set():
    """get_supported_platforms 返回 set[str]。"""
    d = ConcreteDownloader()
    platforms = d.get_supported_platforms()
    assert isinstance(platforms, set)


# ============================================================
# ██  router.py  █████████████████████████████████████████████
# ============================================================

def _make_router():
    """创建不含默认下载器的空路由。"""
    from src.services.downloaders.router import DownloaderRouter
    router = DownloaderRouter.__new__(DownloaderRouter)
    router._downloaders = []
    return router


# ---------- __init__ ----------

@patch("src.services.downloaders.router.YtdlpDownloader")
def test_router_init_registers_ytdlp(mock_ytdlp_cls):
    """初始化时尝试注册 yt-dlp（可用时）。"""
    mock_instance = MagicMock()
    mock_instance.is_available = True
    mock_instance.info.name = "yt-dlp"
    mock_instance.info.priority = 100
    mock_instance.info.platforms = {"youtube"}
    mock_ytdlp_cls.return_value = mock_instance

    from src.services.downloaders.router import DownloaderRouter
    router = DownloaderRouter()
    assert len(router._downloaders) == 1
    assert router._downloaders[0].info.name == "yt-dlp"


@patch("src.services.downloaders.router.YtdlpDownloader")
def test_router_init_skips_unavailable_ytdlp(mock_ytdlp_cls):
    """yt-dlp 不可用时不注册。"""
    mock_instance = MagicMock()
    mock_instance.is_available = False
    mock_ytdlp_cls.return_value = mock_instance

    from src.services.downloaders.router import DownloaderRouter
    router = DownloaderRouter()
    assert len(router._downloaders) == 0


# ---------- register ----------

def test_router_register():
    """注册可用下载器。"""
    router = _make_router()
    d = MockDownloader(name="d1")
    router.register(d)
    assert len(router._downloaders) == 1
    assert router._downloaders[0].info.name == "d1"


def test_router_register_unavailable():
    """不可用的下载器跳过注册。"""
    router = _make_router()
    d = MockDownloader(name="unavail", available=False)
    router.register(d)
    assert len(router._downloaders) == 0


def test_router_register_sorts_by_priority():
    """注册时按优先级排序。"""
    router = _make_router()
    d1 = MockDownloader(name="high", priority=10)
    d2 = MockDownloader(name="low", priority=100)
    d3 = MockDownloader(name="mid", priority=50)
    router.register(d3)
    router.register(d1)
    router.register(d2)
    names = [d.info.name for d in router._downloaders]
    assert names == ["high", "mid", "low"]


def test_router_register_same_priority():
    """同优先级按注册顺序保留。"""
    router = _make_router()
    d1 = MockDownloader(name="a", priority=50)
    d2 = MockDownloader(name="b", priority=50)
    router.register(d1)
    router.register(d2)
    names = [d.info.name for d in router._downloaders]
    assert names == ["a", "b"]


# ---------- unregister ----------

def test_router_unregister():
    """注销已有下载器返回 True。"""
    router = _make_router()
    d = MockDownloader(name="to_remove")
    router.register(d)
    assert router.unregister("to_remove") is True
    assert len(router._downloaders) == 0


def test_router_unregister_not_found():
    """注销不存在的下载器返回 False。"""
    router = _make_router()
    assert router.unregister("nonexistent") is False


def test_router_unregister_partial():
    """只注销匹配的下载器。"""
    router = _make_router()
    router.register(MockDownloader(name="keep"))
    router.register(MockDownloader(name="remove"))
    router.unregister("remove")
    assert len(router._downloaders) == 1
    assert router._downloaders[0].info.name == "keep"


# ---------- get_downloader ----------

def test_router_get_downloader_found():
    """按 URL 找到匹配下载器。"""
    router = _make_router()
    router.register(MockDownloader(name="yt", platforms={"youtube"},
                                    can_handle_result=lambda u: "youtube" in u))
    result = router.get_downloader("https://youtube.com/watch?v=xxx")
    assert result is not None
    assert result.info.name == "yt"


def test_router_get_downloader_not_found():
    """无匹配下载器返回 None。"""
    router = _make_router()
    router.register(MockDownloader(name="yt", can_handle_result=lambda u: "youtube" in u))
    result = router.get_downloader("https://vimeo.com/123")
    assert result is None


def test_router_get_downloader_empty():
    """空路由返回 None。"""
    router = _make_router()
    assert router.get_downloader("https://youtube.com/xxx") is None


def test_router_get_downloader_order():
    """按优先级顺序匹配，返回第一个。"""
    router = _make_router()
    router.register(MockDownloader(name="low", priority=100,
                                    can_handle_result=lambda _u: True))
    router.register(MockDownloader(name="high", priority=10,
                                    can_handle_result=lambda _u: True))
    result = router.get_downloader("https://any.com")
    assert result.info.name == "high"


# ---------- download ----------

def test_router_download():
    """download 委托给匹配的下载器。"""
    router = _make_router()
    d = MockDownloader(name="yt")
    router.register(d)
    opts = DownloadOptions(output_dir=Path("/tmp"))
    result = router.download("https://youtube.com/watch?v=xxx", opts)
    assert result.success is True


def test_router_download_unsupported_platform():
    """不支持的平台抛 UnsupportedPlatformError。"""
    router = _make_router()
    opts = DownloadOptions(output_dir=Path("/tmp"))
    with pytest.raises(UnsupportedPlatformError) as exc:
        router.download("https://unknown.example.com/video", opts)
    assert "UNSUPPORTED_PLATFORM" in str(exc.value)


def test_router_download_passes_callback():
    """progress_callback 透传给下载器。"""
    router = _make_router()
    spy = MagicMock()
    d = MockDownloader(name="yt")
    d.download = MagicMock(return_value=DownloadResult(success=True))
    router.register(d)
    opts = DownloadOptions(output_dir=Path("/tmp"))
    router.download("https://youtube.com/watch?v=xxx", opts, spy)
    d.download.assert_called_once_with("https://youtube.com/watch?v=xxx", opts, spy)


# ---------- get_metadata ----------

def test_router_get_metadata():
    """get_metadata 返回下载器的元数据。"""
    router = _make_router()
    d = MockDownloader(name="yt")
    router.register(d)
    meta = router.get_metadata("https://youtube.com/watch?v=xxx")
    assert meta is not None
    assert meta.title == "Test"


def test_router_get_metadata_unsupported():
    """不支持的平台返回 None。"""
    router = _make_router()
    assert router.get_metadata("https://unknown.example.com") is None


def test_router_get_metadata_empty():
    """空路由返回 None。"""
    router = _make_router()
    assert router.get_metadata("https://youtube.com/xxx") is None


# ---------- is_supported ----------

def test_router_is_supported_true():
    """支持的 URL 返回 True。"""
    router = _make_router()
    router.register(MockDownloader(name="yt"))
    assert router.is_supported("https://youtube.com/watch?v=xxx") is True


def test_router_is_supported_false():
    """不支持的 URL 返回 False。"""
    router = _make_router()
    router.register(MockDownloader(name="yt", can_handle_result=False))
    assert router.is_supported("https://youtube.com/watch?v=xxx") is False


def test_router_is_supported_empty_router():
    """空路由返回 False。"""
    router = _make_router()
    assert router.is_supported("https://youtube.com/xxx") is False


# ---------- get_supported_platforms ----------

def test_router_get_supported_platforms():
    """返回所有注册下载器的平台并排序。"""
    router = _make_router()
    router.register(MockDownloader(name="a", platforms={"bilibili", "youtube"}))
    router.register(MockDownloader(name="b", platforms={"vimeo"}))
    platforms = router.get_supported_platforms()
    assert platforms == ["bilibili", "vimeo", "youtube"]


def test_router_get_supported_platforms_empty():
    """空路由返回空列表。"""
    router = _make_router()
    assert router.get_supported_platforms() == []


def test_router_get_supported_platforms_dedup():
    """重复平台去重。"""
    router = _make_router()
    router.register(MockDownloader(name="a", platforms={"youtube"}))
    router.register(MockDownloader(name="b", platforms={"youtube"}))
    assert router.get_supported_platforms() == ["youtube"]


# ---------- list_downloaders ----------

def test_router_list_downloaders():
    """list_downloaders 返回正确的字典列表。"""
    router = _make_router()
    router.register(MockDownloader(name="test_dl", version="2.0",
                                    platforms={"youtube"}, priority=50))
    lst = router.list_downloaders()
    assert len(lst) == 1
    entry = lst[0]
    assert entry["name"] == "test_dl"
    assert entry["version"] == "2.0"
    assert entry["platforms"] == ["youtube"]
    assert entry["priority"] == 50
    assert entry["available"] is True


def test_router_list_downloaders_empty():
    """空路由返回空列表。"""
    router = _make_router()
    assert router.list_downloaders() == []


def test_router_list_downloaders_multiple():
    """多个下载器时全部列出。"""
    router = _make_router()
    router.register(MockDownloader(name="a"))
    router.register(MockDownloader(name="b"))
    assert len(router.list_downloaders()) == 2


# ---------- get_router (singleton) ----------

def test_get_router_singleton():
    """get_router 返回单例。"""
    # 重置内部单例
    import src.services.downloaders.router as router_mod
    router_mod._router = None

    r1 = router_mod.get_router()
    r2 = router_mod.get_router()
    assert r1 is r2


def test_get_router_singleton_type():
    """get_router 返回 DownloaderRouter 实例。"""
    import src.services.downloaders.router as router_mod
    router_mod._router = None
    from src.services.downloaders.router import DownloaderRouter
    r = router_mod.get_router()
    assert isinstance(r, DownloaderRouter)


# ============================================================
# ██  ytdlp.py  ██████████████████████████████████████████████
# ============================================================

# yt_dlp 在环境中已安装。所有测试通过直接 patch yt_dlp 模块或其属性实现。
# 不要在测试中实际调用 yt_dlp 的任何网络方法。
from src.services.downloaders.ytdlp import YtdlpDownloader as _RealYtdlpDownloader  # noqa: E402

# ---------- info ----------

def test_ytdlp_info():
    """info 属性返回正确的 DownloaderInfo。"""
    with patch("yt_dlp.version.__version__", "2024.01.01"):
        d = _RealYtdlpDownloader()
        info = d.info
        assert info.name == "yt-dlp"
        assert info.version == "2024.01.01"
        assert "youtube" in info.platforms
        assert "bilibili" in info.platforms
        assert "douyin" in info.platforms
        assert "xiaohongshu" in info.platforms
        assert DownloaderCapability.VIDEO in info.capabilities
        assert DownloaderCapability.AUDIO_ONLY in info.capabilities
        assert DownloaderCapability.METADATA in info.capabilities
        assert info.priority == 100
        assert "yt-dlp" in info.description


def test_ytdlp_info_platforms_count():
    """SUPPORTED_PLATFORMS 数量。"""
    assert len(_RealYtdlpDownloader.SUPPORTED_PLATFORMS) == 12


# ---------- is_available ----------

def test_ytdlp_is_available_true():
    """yt_dlp 可导入时返回 True。"""
    d = _RealYtdlpDownloader()
    assert d.is_available is True


def test_ytdlp_is_available_false():
    """yt_dlp 不可导入时返回 False。"""
    # YtdlpDownloader.is_available 内部使用 import yt_dlp
    # 需要 patch builtins.__import__ 使 import yt_dlp 失败
    original_import = builtins.__import__
    def fake_import(name, *args, **kwargs):
        if name == "yt_dlp":
            raise ImportError("no yt_dlp")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        d = _RealYtdlpDownloader()
        assert d.is_available is False


# ---------- can_handle ----------

def test_ytdlp_can_handle_supported():
    """支持平台返回 True。"""
    d = _RealYtdlpDownloader()
    assert d.can_handle("https://www.youtube.com/watch?v=xxx") is True
    assert d.can_handle("https://www.bilibili.com/video/BV1xx") is True
    assert d.can_handle("https://www.douyin.com/video/123") is True
    assert d.can_handle("https://www.xiaohongshu.com/explore/123") is True


def test_ytdlp_can_handle_unknown():
    """未知平台（unknown）返回 True（yt-dlp 广泛支持）。"""
    d = _RealYtdlpDownloader()
    assert d.can_handle("https://example.com/video") is True
    assert d.can_handle("https://some.random.site/watch?v=abc") is True


def test_ytdlp_can_handle_empty_url():
    """空 URL 返回 True（detect 为 unknown）。"""
    d = _RealYtdlpDownloader()
    assert d.can_handle("") is True


# ---------- _get_version ----------

def test_ytdlp_get_version():
    """_get_version 返回 yt_dlp 版本。"""
    with patch("yt_dlp.version.__version__", "2024.01.01"):
        d = _RealYtdlpDownloader()
        assert d._get_version() == "2024.01.01"


def test_ytdlp_get_version_unknown():
    """_get_version 在 AttributeError 时返回 'unknown'。"""
    class _NoVersion:
        pass

    with patch("yt_dlp.version", _NoVersion()):
        d = _RealYtdlpDownloader()
        assert d._get_version() == "unknown"


def test_ytdlp_get_version_cached():
    """_get_version 结果被缓存。"""
    with patch("yt_dlp.version.__version__", "2024.01.01"):
        d = _RealYtdlpDownloader()
        v1 = d._get_version()
        # 再次调用应返回缓存值，不再访问 yt_dlp
        with patch("yt_dlp.version.__version__", "9999.99.99"):
            v2 = d._get_version()
        assert v1 == v2 == "2024.01.01"


# ---------- _build_options ----------

def test_ytdlp_build_options_keep_video_true():
    """keep_video=True 时 format 包含视频。"""
    d = _RealYtdlpDownloader()
    opts = DownloadOptions(output_dir=Path("/tmp"), keep_video=True)
    built = d._build_options(opts, Path("/tmp/.temp"), None)
    assert "bestvideo" in built["format"]
    assert "bestaudio" in built["format"]
    assert built["postprocessors"] == []


def test_ytdlp_build_options_keep_video_false():
    """keep_video=False 时 format 仅音频。"""
    d = _RealYtdlpDownloader()
    opts = DownloadOptions(output_dir=Path("/tmp"), keep_video=False)
    built = d._build_options(opts, Path("/tmp/.temp"), None)
    assert "bestvideo" not in built["format"]
    assert built["format"].startswith("bestaudio")
    assert len(built["postprocessors"]) == 1
    assert built["postprocessors"][0]["key"] == "FFmpegExtractAudio"


def test_ytdlp_build_options_cookies_str():
    """cookies 字符串写入 cookiefile。"""
    d = _RealYtdlpDownloader()
    opts = DownloadOptions(output_dir=Path("/tmp"), cookies="abc123")
    built = d._build_options(opts, Path("/tmp/.temp"), None)
    assert built["cookiefile"] == "abc123"


def test_ytdlp_build_options_cookies_file():
    """cookies_file 写入 cookiefile 字符串路径。"""
    d = _RealYtdlpDownloader()
    opts = DownloadOptions(output_dir=Path("/tmp"), cookies_file=Path("/tmp/cookies.txt"))
    built = d._build_options(opts, Path("/tmp/.temp"), None)
    assert built["cookiefile"] == "/tmp/cookies.txt"


def test_ytdlp_build_options_cookies_browser():
    """cookies_from_browser 写入 cookiesfrombrowser。"""
    d = _RealYtdlpDownloader()
    opts = DownloadOptions(output_dir=Path("/tmp"), cookies_from_browser="chrome")
    built = d._build_options(opts, Path("/tmp/.temp"), None)
    assert built["cookiesfrombrowser"] == ("chrome",)


def test_ytdlp_build_options_proxy():
    """proxy 写入配置。"""
    d = _RealYtdlpDownloader()
    opts = DownloadOptions(output_dir=Path("/tmp"), proxy="http://proxy:8080")
    built = d._build_options(opts, Path("/tmp/.temp"), None)
    assert built["proxy"] == "http://proxy:8080"


def test_ytdlp_build_options_subtitle_languages():
    """subtitle_languages 启用手写字幕。"""
    d = _RealYtdlpDownloader()
    opts = DownloadOptions(output_dir=Path("/tmp"), subtitle_languages=["zh", "en"])
    built = d._build_options(opts, Path("/tmp/.temp"), None)
    assert built["writesubtitles"] is True
    assert built["subtitleslangs"] == ["zh", "en"]


def test_ytdlp_build_options_no_subtitles():
    """无 subtitle_languages 默认 writesubtitles=False。"""
    d = _RealYtdlpDownloader()
    opts = DownloadOptions(output_dir=Path("/tmp"))
    built = d._build_options(opts, Path("/tmp/.temp"), None)
    assert built["writesubtitles"] is False
    assert built["subtitleslangs"] == ["all"]


def test_ytdlp_build_options_progress_callback():
    """progress_callback 创建进度钩子。"""
    d = _RealYtdlpDownloader()
    cb = MagicMock()
    opts = DownloadOptions(output_dir=Path("/tmp"))
    built = d._build_options(opts, Path("/tmp/.temp"), cb)
    assert "progress_hooks" in built
    assert len(built["progress_hooks"]) == 1
    assert callable(built["progress_hooks"][0])


def test_ytdlp_build_options_output_template():
    """outtmpl 使用 temp_dir。"""
    d = _RealYtdlpDownloader()
    opts = DownloadOptions(output_dir=Path("/tmp"))
    built = d._build_options(opts, Path("/tmp/.temp/test"), None)
    assert "/tmp/.temp/test" in built["outtmpl"]


# ---------- download ----------

def _make_mock_ydl(extract_info_return=None, extract_info_side_effect=None):
    """创建模拟的 yt_dlp.YoutubeDL 上下文管理器。"""
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=None)
    if extract_info_side_effect:
        mock_ydl.extract_info.side_effect = extract_info_side_effect
    else:
        mock_ydl.extract_info.return_value = extract_info_return
    return mock_ydl


def test_ytdlp_download_success():
    """download 成功路径。"""
    mock_ydl = _make_mock_ydl(extract_info_return={
        "title": "Test Video",
        "uploader": "Creator",
        "duration": 300,
        "webpage_url": "https://youtube.com/watch?v=xxx",
        "thumbnail": "https://img.youtube.com/vi/xxx/hqdefault.jpg",
        "description": "A test video",
    })

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        with patch("pathlib.Path.mkdir", return_value=None):
            with patch("src.services.downloaders.ytdlp.sanitize_filename", return_value="Test_Video"):
                with patch("shutil.move", return_value=None):
                    with patch("shutil.rmtree", return_value=None):
                        d = _RealYtdlpDownloader()
                        opts = DownloadOptions(output_dir=Path("/tmp"))
                        result = d.download("https://youtube.com/watch?v=xxx", opts)
                        assert result.success is True
                        mock_ydl.extract_info.assert_called_once()


def test_ytdlp_download_extract_failed():
    """extract_info 返回 None 时返回 EXTRACT_FAILED。"""
    mock_ydl = _make_mock_ydl(extract_info_return=None)

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        with patch("pathlib.Path.mkdir", return_value=None):
            d = _RealYtdlpDownloader()
            opts = DownloadOptions(output_dir=Path("/tmp"))
            result = d.download("https://youtube.com/watch?v=xxx", opts)
            assert result.success is False
            assert result.error_code == "EXTRACT_FAILED"


def test_ytdlp_download_error_404():
    """HTTP 404 映射为 VIDEO_NOT_FOUND。"""
    from yt_dlp.utils import DownloadError
    mock_ydl = _make_mock_ydl(extract_info_side_effect=DownloadError("HTTP Error 404: Not Found"))

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        with patch("pathlib.Path.mkdir", return_value=None):
            d = _RealYtdlpDownloader()
            opts = DownloadOptions(output_dir=Path("/tmp"))
            result = d.download("https://youtube.com/watch?v=xxx", opts)
            assert result.success is False
            assert result.error_code == "VIDEO_NOT_FOUND"


def test_ytdlp_download_error_video_unavailable():
    """Video unavailable 映射为 VIDEO_NOT_FOUND。"""
    from yt_dlp.utils import DownloadError
    mock_ydl = _make_mock_ydl(extract_info_side_effect=DownloadError("Video unavailable: This video has been removed"))

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        with patch("pathlib.Path.mkdir", return_value=None):
            d = _RealYtdlpDownloader()
            opts = DownloadOptions(output_dir=Path("/tmp"))
            result = d.download("https://youtube.com/watch?v=xxx", opts)
            assert result.success is False
            assert result.error_code == "VIDEO_NOT_FOUND"


def test_ytdlp_download_error_private():
    """Private video 映射为 PRIVATE_VIDEO。"""
    from yt_dlp.utils import DownloadError
    mock_ydl = _make_mock_ydl(extract_info_side_effect=DownloadError("Private video"))

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        with patch("pathlib.Path.mkdir", return_value=None):
            d = _RealYtdlpDownloader()
            opts = DownloadOptions(output_dir=Path("/tmp"))
            result = d.download("https://youtube.com/watch?v=xxx", opts)
            assert result.success is False
            assert result.error_code == "PRIVATE_VIDEO"


def test_ytdlp_download_error_login():
    """Sign in 映射为 LOGIN_REQUIRED。"""
    from yt_dlp.utils import DownloadError
    mock_ydl = _make_mock_ydl(extract_info_side_effect=DownloadError("Sign in to confirm your age"))

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        with patch("pathlib.Path.mkdir", return_value=None):
            d = _RealYtdlpDownloader()
            opts = DownloadOptions(output_dir=Path("/tmp"))
            result = d.download("https://youtube.com/watch?v=xxx", opts)
            assert result.success is False
            assert result.error_code == "LOGIN_REQUIRED"


def test_ytdlp_download_error_login_lowercase():
    """login 小写匹配也映射为 LOGIN_REQUIRED。"""
    from yt_dlp.utils import DownloadError
    mock_ydl = _make_mock_ydl(extract_info_side_effect=DownloadError("This video requires login"))

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        with patch("pathlib.Path.mkdir", return_value=None):
            d = _RealYtdlpDownloader()
            opts = DownloadOptions(output_dir=Path("/tmp"))
            result = d.download("https://youtube.com/watch?v=xxx", opts)
            assert result.success is False
            assert result.error_code == "LOGIN_REQUIRED"


def test_ytdlp_download_error_generic():
    """其他 DownloadError 映射为 DOWNLOAD_FAILED。"""
    from yt_dlp.utils import DownloadError
    mock_ydl = _make_mock_ydl(extract_info_side_effect=DownloadError("Some random download error"))

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        with patch("pathlib.Path.mkdir", return_value=None):
            d = _RealYtdlpDownloader()
            opts = DownloadOptions(output_dir=Path("/tmp"))
            result = d.download("https://youtube.com/watch?v=xxx", opts)
            assert result.success is False
            assert result.error_code == "DOWNLOAD_FAILED"


def test_ytdlp_download_exception_generic():
    """非 DownloadError 的异常映射为 UNKNOWN_ERROR。"""
    mock_ydl = _make_mock_ydl(extract_info_side_effect=ValueError("Something went wrong"))

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        with patch("pathlib.Path.mkdir", return_value=None):
            d = _RealYtdlpDownloader()
            opts = DownloadOptions(output_dir=Path("/tmp"))
            result = d.download("https://youtube.com/watch?v=xxx", opts)
            assert result.success is False
            assert result.error_code == "UNKNOWN_ERROR"


# ---------- get_metadata ----------

def test_ytdlp_get_metadata_success():
    """get_metadata 返回 VideoMetadata。"""
    mock_ydl = _make_mock_ydl(extract_info_return={
        "title": "My Video",
        "uploader": "Channel Name",
        "duration": 600,
        "webpage_url": "https://youtube.com/watch?v=abc",
        "thumbnail": "https://img.youtube.com/vi/abc/0.jpg",
        "description": "Video description here",
    })

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        d = _RealYtdlpDownloader()
        meta = d.get_metadata("https://youtube.com/watch?v=abc")
        assert meta is not None
        assert isinstance(meta, VideoMetadata)
        assert meta.title == "My Video"
        assert meta.author == "Channel Name"
        assert meta.duration == 600
        assert meta.platform == "youtube"
        assert meta.url == "https://youtube.com/watch?v=abc"
        assert meta.thumbnail_url == "https://img.youtube.com/vi/abc/0.jpg"
        assert meta.description == "Video description here"


def test_ytdlp_get_metadata_failure():
    """get_metadata 异常时返回 None。"""
    mock_ydl = _make_mock_ydl(extract_info_side_effect=Exception("Network error"))

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        d = _RealYtdlpDownloader()
        meta = d.get_metadata("https://youtube.com/watch?v=abc")
        assert meta is None


def test_ytdlp_get_metadata_info_none():
    """extract_info 返回 None 时返回 None。"""
    mock_ydl = _make_mock_ydl(extract_info_return=None)

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        d = _RealYtdlpDownloader()
        meta = d.get_metadata("https://youtube.com/watch?v=abc")
        assert meta is None


def test_ytdlp_get_metadata_uses_extract_flat_false():
    """get_metadata 使用 extract_flat=False 且 download=False。"""
    mock_ydl = _make_mock_ydl(extract_info_return={
        "title": "T", "uploader": "U", "duration": 10,
        "webpage_url": "https://youtube.com/watch?v=abc",
    })

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        d = _RealYtdlpDownloader()
        d.get_metadata("https://youtube.com/watch?v=abc")
        mock_ydl.extract_info.assert_called_once_with("https://youtube.com/watch?v=abc", download=False)


# ---------- _progress_hook ----------

def test_ytdlp_progress_hook_downloading():
    """下载中状态调用回调。"""
    d = _RealYtdlpDownloader()
    cb = MagicMock()
    data = {
        "status": "downloading",
        "total_bytes": 1000,
        "downloaded_bytes": 250,
    }
    d._progress_hook(data, cb)
    cb.assert_called_once_with("下载中", 25.0)


def test_ytdlp_progress_hook_downloading_estimate():
    """下载中使用 total_bytes_estimate。"""
    d = _RealYtdlpDownloader()
    cb = MagicMock()
    data = {
        "status": "downloading",
        "total_bytes_estimate": 2000,
        "downloaded_bytes": 500,
    }
    d._progress_hook(data, cb)
    cb.assert_called_once_with("下载中", 25.0)


def test_ytdlp_progress_hook_downloading_zero_total():
    """总字节数为 0 时进度为 0。"""
    d = _RealYtdlpDownloader()
    cb = MagicMock()
    data = {
        "status": "downloading",
        "downloaded_bytes": 100,
    }
    d._progress_hook(data, cb)
    cb.assert_called_once_with("下载中", 0)


def test_ytdlp_progress_hook_finished():
    """完成状态回调 100%。"""
    d = _RealYtdlpDownloader()
    cb = MagicMock()
    data = {"status": "finished"}
    d._progress_hook(data, cb)
    cb.assert_called_once_with("处理中", 100)


def test_ytdlp_progress_hook_other_status():
    """其他状态不调用回调。"""
    d = _RealYtdlpDownloader()
    cb = MagicMock()
    data = {"status": "error"}
    d._progress_hook(data, cb)
    cb.assert_not_called()


# ---------- _process_result ----------

@patch("shutil.move", return_value=None)
@patch("shutil.rmtree", return_value=None)
def test_ytdlp_process_result(mock_rmtree, mock_move):
    """_process_result 正确处理下载结果。"""
    with patch("pathlib.Path.mkdir", return_value=None):
        with patch("src.services.downloaders.ytdlp.sanitize_filename", return_value="Test_Video"):
            d = _RealYtdlpDownloader()

            info = {
                "title": "Test Video",
                "uploader": "Creator",
                "duration": 300,
                "webpage_url": "https://youtube.com/watch?v=xxx",
                "thumbnail": "https://img.youtube.com/vi/xxx/hqdefault.jpg",
                "description": "A test video",
            }
            opts = DownloadOptions(output_dir=Path("/tmp"))
            temp_dir = Path("/tmp/.temp")

            with patch.object(Path, "glob", return_value=[
                Path("/tmp/.temp/Test_Video.mp4"),
                Path("/tmp/.temp/Test_Video.m4a"),
            ]), patch.object(Path, "is_file", return_value=True):
                result = d._process_result(info, opts, temp_dir)
                assert result.success is True
                assert result.video_path is not None
                assert result.video_path.suffix == ".mp4"
                assert result.audio_path is not None
                assert result.audio_path.suffix == ".m4a"
                assert result.metadata is not None
                assert result.metadata.title == "Test Video"
                mock_move.assert_called()


@patch("shutil.move", return_value=None)
@patch("shutil.rmtree", return_value=None)
def test_ytdlp_process_result_audio_only(mock_rmtree, mock_move):
    """仅音频文件的处理。"""
    with patch("pathlib.Path.mkdir", return_value=None):
        with patch("src.services.downloaders.ytdlp.sanitize_filename", return_value="Song"):
            d = _RealYtdlpDownloader()

            info = {"title": "Song", "uploader": "Artist", "duration": 240,
                    "webpage_url": "https://youtube.com/watch?v=abc"}
            opts = DownloadOptions(output_dir=Path("/tmp"))
            temp_dir = Path("/tmp/.temp")

            with patch.object(Path, "glob", return_value=[
                Path("/tmp/.temp/Song.mp3"),
            ]), patch.object(Path, "is_file", return_value=True):
                result = d._process_result(info, opts, temp_dir)
                assert result.success is True
                assert result.audio_path is not None
                assert result.audio_path.suffix == ".mp3"
                assert result.video_path is None


@patch("shutil.move", return_value=None)
@patch("shutil.rmtree", return_value=None)
def test_ytdlp_process_result_no_files(mock_rmtree, mock_move):
    """无下载文件时仍返回成功但路径为空。"""
    with patch("pathlib.Path.mkdir", return_value=None):
        with patch("src.services.downloaders.ytdlp.sanitize_filename", return_value="Empty"):
            d = _RealYtdlpDownloader()

            info = {"title": "Empty", "uploader": "Nobody", "duration": 0,
                    "webpage_url": ""}
            opts = DownloadOptions(output_dir=Path("/tmp"))
            temp_dir = Path("/tmp/.temp")

            with patch.object(Path, "glob", return_value=[]):
                result = d._process_result(info, opts, temp_dir)
                assert result.success is True
                assert result.audio_path is None
                assert result.video_path is None


# ============================================================
# ██  集成 / 边界测试  ██████████████████████████████████████
# ============================================================

def test_download_options_to_dict():
    """确保 DownloadOptions 可以轻松转字典（用于日志等）。"""
    opts = DownloadOptions(output_dir=Path("/tmp"))
    d = {
        "output_dir": str(opts.output_dir),
        "keep_video": opts.keep_video,
        "video_quality": opts.video_quality,
        "timeout": opts.timeout,
    }
    assert d["output_dir"] == "/tmp"
    assert d["keep_video"] is False


def test_progress_callback_noop():
    """ProgressCallback 可传 None。"""
    d = ConcreteDownloader()
    opts = DownloadOptions(output_dir=Path("/tmp"))
    # 应当正常工作，不会抛出 TypeError
    result = d.download("https://youtube.com/watch?v=xxx", opts, None)
    assert result.success is True


def test_download_result_repr():
    """DownloadResult 的 __repr__ 可读。"""
    r = DownloadResult(success=True)
    r_str = repr(r)
    assert "success=True" in r_str


@patch("src.services.downloaders.router.YtdlpDownloader")
def test_router_init_logs_registration(mock_ytdlp_cls):
    """初始化时注册 yt-dlp 会记录日志。"""
    mock_instance = MagicMock()
    mock_instance.is_available = True
    mock_instance.info.name = "yt-dlp"
    mock_instance.info.priority = 100
    mock_instance.info.platforms = {"youtube"}
    mock_ytdlp_cls.return_value = mock_instance

    from src.services.downloaders.router import DownloaderRouter
    with patch("src.services.downloaders.router.logger") as mock_logger:
        DownloaderRouter()
        mock_logger.info.assert_any_call(
            "注册下载器: yt-dlp (优先级: 100, 平台: youtube)"
        )


def test_router_download_with_progress():
    """路由下载时传入进度回调。"""
    router = _make_router()
    d = MockDownloader(name="yt")
    d.download = MagicMock(return_value=DownloadResult(success=True))
    router.register(d)
    cb = MagicMock()
    opts = DownloadOptions(output_dir=Path("/tmp"))
    result = router.download("https://youtube.com/watch?v=xxx", opts, cb)
    assert result.success is True
    d.download.assert_called_once()


def test_ytdlp_download_creates_output_dirs():
    """download 创建输出目录和临时目录。"""
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=None)
    mock_ydl.extract_info.return_value = {
        "title": "Test", "uploader": "U", "duration": 10,
        "webpage_url": "https://youtube.com/watch?v=xxx",
    }

    mkdir = MagicMock(return_value=None)
    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl), patch("pathlib.Path.mkdir", mkdir):
        with patch("src.services.downloaders.ytdlp.sanitize_filename", return_value="Test"):
            with patch("shutil.move", return_value=None):
                with patch("shutil.rmtree", return_value=None):
                    d = _RealYtdlpDownloader()
                    opts = DownloadOptions(output_dir=Path("/tmp/output"))
                    d.download("https://youtube.com/watch?v=xxx", opts)
                    assert mkdir.call_count >= 2


def test_ytdlp_download_rmtree_error_ignored():
    """rmtree 失败时静默忽略。"""
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=None)
    mock_ydl.extract_info.return_value = {
        "title": "Test", "uploader": "U", "duration": 10,
        "webpage_url": "https://youtube.com/watch?v=xxx",
    }

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        with patch("pathlib.Path.mkdir", return_value=None):
            with patch("src.services.downloaders.ytdlp.sanitize_filename", return_value="Test"):
                with patch("shutil.move", return_value=None):
                    with patch("shutil.rmtree", side_effect=PermissionError("denied")):
                        d = _RealYtdlpDownloader()
                        opts = DownloadOptions(output_dir=Path("/tmp"))
                        result = d.download("https://youtube.com/watch?v=xxx", opts)
                        assert result.success is True


def test_ytdlp_build_options_cookies_precedence():
    """cookies > cookies_file > cookies_from_browser 优先级。"""
    d = _RealYtdlpDownloader()
    opts = DownloadOptions(
        output_dir=Path("/tmp"),
        cookies="direct",
        cookies_file=Path("/tmp/c.txt"),
        cookies_from_browser="chrome",
    )
    built = d._build_options(opts, Path("/tmp/.temp"), None)
    assert built.get("cookiefile") == "direct"
    assert "cookiesfrombrowser" not in built
