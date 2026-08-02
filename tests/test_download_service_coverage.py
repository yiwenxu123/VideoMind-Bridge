"""覆盖 DownloadService 缺失错误路径的测试"""
from pathlib import Path
from unittest import mock

import pytest

from src.services.download_service import DownloadService
from src.utils.exceptions import DownloadError, UnsupportedPlatformError


@pytest.fixture
def service(tmp_path):
    svc = DownloadService(output_dir=tmp_path)
    svc._router = mock.MagicMock()
    svc._router.download.return_value = mock.MagicMock(
        success=True, audio_path=Path("/tmp/audio.mp3"),
        video_path=None, metadata=None, error_message=None, error_code=None,
    )
    return svc


class TestDownloadRetryLogic:
    """download 方法重试逻辑"""

    def test_unsupported_platform_raised_immediately(self, service):
        with mock.patch.object(service, "_do_download", side_effect=UnsupportedPlatformError("不支持的平台")):
            with pytest.raises(UnsupportedPlatformError):
                service.download("https://unknown.com/video")

    def test_non_retryable_error_raised_immediately(self, service):
        for code in ["VIDEO_NOT_FOUND", "AGE_RESTRICTED", "REGION_BLOCKED", "PRIVATE_VIDEO"]:
            with mock.patch.object(service, "_do_download", side_effect=DownloadError("blocked", error_code=code)):
                with pytest.raises(DownloadError):
                    service.download("https://example.com/video")

    def test_all_retries_exhausted(self, service):
        with mock.patch.object(service, "_do_download", side_effect=DownloadError("network timeout", error_code="NETWORK_ERROR")):
            with pytest.raises(DownloadError) as excinfo:
                service.download("https://example.com/video")
            assert "重试" in str(excinfo.value)

    def test_retry_then_succeed(self, service):
        fake_result = mock.MagicMock()
        fake_result.success = True
        fake_result.audio_path = Path("/tmp/audio.mp3")
        fake_result.video_path = None
        fake_result.metadata = None
        fake_result.error_message = None
        fake_result.error_code = None

        with mock.patch.object(service, "_do_download", side_effect=[
            DownloadError("transient", error_code="NETWORK_ERROR"),
            fake_result,
        ]), mock.patch.object(service, "_detect_platform", return_value="youtube"):
            result = service.download("https://example.com/video")
            assert result.audio_path == Path("/tmp/audio.mp3")


class TestDoDownload:
    """_do_download 错误路径"""

    @pytest.fixture
    def mock_router_result(self):
        r = mock.MagicMock()
        r.success = True
        r.audio_path = Path("/tmp/audio.mp3")
        r.video_path = None
        r.metadata = None
        r.error_message = None
        r.error_code = None
        return r

    def test_do_download_calls_progress_callback(self, service, mock_router_result):
        service._router.download.return_value = mock_router_result
        callback = mock.MagicMock()
        with mock.patch.object(service, "_detect_platform", return_value="youtube"):
            service._do_download("https://x.com", True, "best", callback)
        callback.assert_any_call("正在选择下载器...", 2)

    def test_do_download_router_fails(self, service):
        service._router.download.return_value = mock.MagicMock(
            success=False, error_message="downloader error", error_code="ROUTER_FAILED"
        )
        with pytest.raises(DownloadError) as excinfo:
            service._do_download("https://x.com", True, "best", None)
        assert "downloader error" in str(excinfo.value)

    def test_do_download_audio_path_none(self, service):
        service._router.download.return_value = mock.MagicMock(
            success=True, audio_path=None, error_message=None, error_code=None
        )
        with pytest.raises(DownloadError) as excinfo:
            service._do_download("https://x.com", True, "best", None)
        assert "音频文件" in str(excinfo.value)

    def test_do_download_metadata_none_creates_default(self, service):
        result = mock.MagicMock()
        result.success = True
        result.audio_path = Path("/tmp/audio.mp3")
        result.video_path = None
        result.metadata = None
        service._router.download.return_value = result

        with mock.patch.object(service, "_detect_platform", return_value="bilibili"):
            dl_result = service._do_download("https://bilibili.com/video", True, "best", None)

        assert dl_result.metadata.platform == "bilibili"
        assert dl_result.metadata.title == "未知标题"

    def test_do_download_with_video_path(self, service):
        result = mock.MagicMock()
        result.success = True
        result.audio_path = Path("/tmp/audio.mp3")
        result.video_path = Path("/tmp/video.mp4")
        result.metadata = "not_used"
        service._router.download.return_value = result

        with mock.patch.object(service, "_detect_platform", return_value="youtube"):
            dl_result = service._do_download("https://youtube.com/watch?v=x", True, "best", None)

        assert dl_result.video_path == Path("/tmp/video.mp4")
        assert dl_result.audio_path == Path("/tmp/audio.mp3")


class TestServiceMethods:
    """轻量方法测试"""

    def test_get_supported_platforms(self, service):
        service._router.get_supported_platforms.return_value = ["youtube", "bilibili"]
        result = service.get_supported_platforms()
        assert result == ["youtube", "bilibili"]

    def test_is_supported(self, service):
        service._router.is_supported.return_value = True
        assert service.is_supported("https://youtube.com/watch?v=x") is True

    def test_get_metadata(self, service):
        fake_meta = mock.MagicMock()
        service._router.get_metadata.return_value = fake_meta
        result = service.get_metadata("https://youtube.com/watch?v=x")
        assert result is fake_meta

    def test_list_downloaders(self, service):
        service._router.list_downloaders.return_value = [{"name": "yt-dlp"}]
        result = service.list_downloaders()
        assert result == [{"name": "yt-dlp"}]

    def test_retry_with_progress_callback(self, service):
        callback = mock.MagicMock()
        with mock.patch.object(service, "_do_download", side_effect=DownloadError("timeout", error_code="NETWORK_ERROR")):
            with pytest.raises(DownloadError):
                service.download("https://x.com", progress_callback=callback)
        retry_calls = [c for c in callback.call_args_list if "重试" in str(c)]
        assert len(retry_calls) > 0
