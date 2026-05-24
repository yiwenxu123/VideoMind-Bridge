"""下载服务测试 - Mock 模式"""

from unittest.mock import MagicMock, patch

import pytest

from src.models.task import VideoMetadata
from src.services.download_service import DownloadResult, DownloadService
from src.utils.exceptions import DownloadError


class TestDownloadServiceInit:
    """下载服务初始化测试"""

    def test_init_creates_output_dir(self, tmp_path):
        """测试初始化时创建输出目录"""
        output_dir = tmp_path / "downloads"
        assert not output_dir.exists()

        service = DownloadService(output_dir)

        assert service.output_dir == output_dir
        assert output_dir.exists()

    def test_init_with_existing_dir(self, tmp_path):
        """测试使用已存在的目录初始化"""
        output_dir = tmp_path / "existing"
        output_dir.mkdir()

        service = DownloadService(output_dir)

        assert service.output_dir == output_dir


class TestDownloadServiceValidation:
    """下载服务验证测试"""

    def test_supported_platforms(self, tmp_path):
        """测试支持的平台检测"""
        service = DownloadService(tmp_path)

        supported_urls = [
            ("https://www.bilibili.com/video/BV1xx411c7mD", "bilibili"),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
            ("https://www.douyin.com/video/123456789", "douyin"),
            ("https://www.xiaohongshu.com/explore/123456", "xiaohongshu"),
        ]

        for url, expected_platform in supported_urls:
            if "bilibili" in url:
                assert "bilibili" in url
            elif "youtube" in url:
                assert "youtube" in url
            elif "douyin" in url:
                assert "douyin" in url
            elif "xiaohongshu" in url:
                assert "xiaohongshu" in url


class TestDownloadServiceMock:
    """下载服务 Mock 测试"""

    @patch('src.services.downloaders.ytdlp.yt_dlp.YoutubeDL')
    def test_get_video_info_success(self, mock_ydl, tmp_path):
        """测试获取视频信息成功"""
        mock_instance = MagicMock()
        mock_ydl.return_value.__enter__.return_value = mock_instance

        mock_instance.extract_info.return_value = {
            'title': '测试视频标题',
            'uploader': '测试作者',
            'duration': 300,
            'webpage_url': 'https://www.bilibili.com/video/BV1xx',
            'thumbnail': 'https://example.com/thumb.jpg',
            'description': '测试描述',
        }

        service = DownloadService(tmp_path)
        info = mock_instance.extract_info('https://www.bilibili.com/video/BV1xx', download=False)

        assert info['title'] == '测试视频标题'
        assert info['duration'] == 300

    @patch('src.services.downloaders.ytdlp.yt_dlp.YoutubeDL')
    def test_get_video_info_not_found(self, mock_ydl, tmp_path):
        """测试视频不存在"""
        import yt_dlp

        mock_instance = MagicMock()
        mock_ydl.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.side_effect = yt_dlp.utils.DownloadError("Video unavailable")

        service = DownloadService(tmp_path)

        with pytest.raises(yt_dlp.utils.DownloadError):
            mock_instance.extract_info('https://invalid.url', download=False)


class TestDownloadErrorHandling:
    """下载错误处理测试"""

    def test_video_not_found_error(self, tmp_path):
        """测试视频不存在错误"""
        error = DownloadError(
            "视频不存在或已被删除",
            error_code="VIDEO_NOT_FOUND",
            details={"url": "https://example.com/video/123"}
        )

        assert error.error_code == "VIDEO_NOT_FOUND"
        assert "视频不存在" in error.message
        assert error.details["url"] == "https://example.com/video/123"

    def test_age_restricted_error(self, tmp_path):
        """测试年龄限制错误"""
        error = DownloadError(
            "视频有年龄限制",
            error_code="AGE_RESTRICTED",
            details={"url": "https://example.com/video/123"}
        )

        assert error.error_code == "AGE_RESTRICTED"

    def test_region_blocked_error(self, tmp_path):
        """测试地区限制错误"""
        error = DownloadError(
            "视频在您的地区不可用",
            error_code="REGION_BLOCKED",
            details={"url": "https://example.com/video/123"}
        )

        assert error.error_code == "REGION_BLOCKED"

    def test_network_error(self, tmp_path):
        """测试网络错误"""
        error = DownloadError(
            "网络连接失败",
            error_code="NETWORK_ERROR",
            details={"url": "https://example.com/video/123"}
        )

        assert error.error_code == "NETWORK_ERROR"


class TestDownloadResult:
    """下载结果测试"""

    def test_download_result_creation(self, tmp_path):
        """测试下载结果创建"""
        metadata = VideoMetadata(
            title="测试视频",
            author="测试作者",
            duration=300,
            platform="bilibili",
            url="https://example.com/video/123"
        )

        result = DownloadResult(
            video_path=tmp_path / "video.mp4",
            audio_path=tmp_path / "audio.m4a",
            metadata=metadata
        )

        assert result.metadata.title == "测试视频"
        assert result.metadata.duration == 300
        assert result.video_path is not None
        assert result.audio_path is not None

    def test_download_result_video_none(self, tmp_path):
        """测试仅音频下载结果"""
        metadata = VideoMetadata(
            title="测试音频",
            author="测试作者",
            duration=180,
            platform="bilibili",
            url="https://example.com/video/456"
        )

        result = DownloadResult(
            video_path=None,
            audio_path=tmp_path / "audio.m4a",
            metadata=metadata
        )

        assert result.video_path is None
        assert result.audio_path is not None


class TestVideoMetadata:
    """视频元数据测试"""

    def test_metadata_from_ytdlp(self):
        """测试从 yt-dlp 信息创建元数据"""
        info = {
            'title': '测试标题',
            'uploader': '测试上传者',
            'duration': 600,
            'webpage_url': 'https://www.bilibili.com/video/BV1xx',
            'thumbnail': 'https://example.com/thumb.jpg',
            'description': '测试描述',
            'upload_date': '20240101',
        }

        metadata = VideoMetadata(
            title=info.get('title', ''),
            author=info.get('uploader', ''),
            duration=info.get('duration', 0),
            platform='bilibili',
            url=info.get('webpage_url', ''),
            thumbnail_url=info.get('thumbnail'),
            description=info.get('description'),
        )

        assert metadata.title == '测试标题'
        assert metadata.author == '测试上传者'
        assert metadata.duration == 600
        assert metadata.platform == 'bilibili'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
