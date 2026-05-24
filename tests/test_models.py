"""数据模型测试"""

import sys
from pathlib import Path

from src.models.task import (
    VideoMetadata, ProcessingMode, ExportTarget,
    TaskStatus, ExportContext, ExportResult, TranscriptSegment
)
from src.models.config import AppConfig, AIConfig, DownloadConfig


def test_video_metadata():
    """测试 VideoMetadata 模型"""
    print("=== 测试 VideoMetadata ===")
    
    metadata = VideoMetadata(
        title="测试视频",
        author="测试作者",
        duration=120,
        platform="bilibili",
        url="https://test.com/video"
    )
    
    assert metadata.title == "测试视频"
    assert metadata.author == "测试作者"
    assert metadata.duration == 120
    assert metadata.platform == "bilibili"
    
    print("  ✓ VideoMetadata 测试通过")


def test_processing_mode():
    """测试 ProcessingMode 枚举"""
    print("\n=== 测试 ProcessingMode ===")
    
    assert ProcessingMode.FULL.value == "full"
    assert ProcessingMode.DOWNLOAD_ONLY.value == "download_only"
    assert ProcessingMode.TRANSCRIBE_ONLY.value == "transcribe_only"
    
    # 测试从字符串创建
    mode = ProcessingMode("full")
    assert mode == ProcessingMode.FULL
    
    print("  ✓ ProcessingMode 测试通过")


def test_export_target():
    """测试 ExportTarget 枚举"""
    print("\n=== 测试 ExportTarget ===")
    
    assert ExportTarget.LOCAL.value == "local"
    assert ExportTarget.OBSIDIAN.value == "obsidian"
    assert ExportTarget.NOTION.value == "notion"
    
    print("  ✓ ExportTarget 测试通过")


def test_task_status():
    """测试 TaskStatus 枚举"""
    print("\n=== 测试 TaskStatus ===")
    
    statuses = [
        TaskStatus.PENDING,
        TaskStatus.DOWNLOADING,
        TaskStatus.TRANSCRIBING,
        TaskStatus.AI_PROCESSING,
        TaskStatus.EXPORTING,
        TaskStatus.PAUSED,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED
    ]
    
    assert len(statuses) == 9
    for status in statuses:
        assert isinstance(status.value, str)
    
    print("  ✓ TaskStatus 测试通过")


def test_transcript_segment():
    """测试 TranscriptSegment 模型"""
    print("\n=== 测试 TranscriptSegment ===")
    
    segment = TranscriptSegment(
        start=0.0,
        end=5.0,
        text="测试字幕"
    )
    
    assert segment.start == 0.0
    assert segment.end == 5.0
    assert segment.text == "测试字幕"
    
    print("  ✓ TranscriptSegment 测试通过")


def test_export_result():
    """测试 ExportResult 模型"""
    print("\n=== 测试 ExportResult ===")
    
    result = ExportResult(
        success=True,
        target=ExportTarget.LOCAL,
        output_path="/test/output",
        error_msg=None
    )
    
    assert result.success is True
    assert result.target == ExportTarget.LOCAL
    assert result.output_path == "/test/output"
    
    # 测试失败结果
    failed_result = ExportResult(
        success=False,
        target=ExportTarget.LOCAL,
        error_msg="测试错误"
    )
    
    assert failed_result.success is False
    assert failed_result.error_msg == "测试错误"
    
    print("  ✓ ExportResult 测试通过")


def test_export_context():
    """测试 ExportContext 模型"""
    print("\n=== 测试 ExportContext ===")
    
    from uuid import uuid4
    from datetime import datetime
    
    task_id = uuid4()
    metadata = VideoMetadata(
        title="测试视频",
        author="测试作者",
        duration=120,
        platform="bilibili",
        url="https://test.com"
    )
    
    context = ExportContext(
        task_id=task_id,
        video_metadata=metadata,
        video_path=Path("/test/video.mp4"),
        audio_path=Path("/test/audio.m4a"),
        transcript_text="测试转录内容",
        transcript_segments=[
            TranscriptSegment(0, 5, "第一句"),
            TranscriptSegment(5, 10, "第二句"),
        ],
        ai_summary="测试摘要"
    )
    
    assert context.task_id == task_id
    assert context.video_metadata.title == "测试视频"
    assert len(context.transcript_segments) == 2
    
    print("  ✓ ExportContext 测试通过")


def test_app_config():
    """测试 AppConfig 模型"""
    print("\n=== 测试 AppConfig ===")
    
    config = AppConfig.get_default_config()
    
    # 检查默认配置
    assert config.version == "1"
    assert config.download.output_dir == str(Path.home() / "Downloads" / "VideoMind")
    assert isinstance(config.ai, AIConfig)
    assert isinstance(config.download, DownloadConfig)
    
    # 测试配置序列化
    config_dict = config.to_dict()
    assert "ai" in config_dict
    assert "download" in config_dict
    
    # 测试配置反序列化
    restored_config = AppConfig.from_dict(config_dict)
    assert restored_config.ai.engine == config.ai.engine
    
    print("  ✓ AppConfig 测试通过")


def test_ai_config():
    """测试 AIConfig 模型"""
    print("\n=== 测试 AIConfig ===")
    
    config = AIConfig()
    
    assert config.engine.value == "DeepSeek-V3"
    assert config.api_key == ""
    assert config.model == "deepseek-chat"
    assert config.temperature == 0.7
    assert config.max_tokens == 4096
    
    print("  ✓ AIConfig 测试通过")


def test_download_config():
    """测试 DownloadConfig 模型"""
    print("\n=== 测试 DownloadConfig ===")
    
    config = DownloadConfig()
    
    assert config.video_quality == "1080p"
    assert config.download_video is True
    assert config.organize_by == "date"
    
    print("  ✓ DownloadConfig 测试通过")


if __name__ == "__main__":
    print("=" * 50)
    print("数据模型测试套件")
    print("=" * 50)
    
    all_passed = True
    all_passed &= test_video_metadata()
    all_passed &= test_processing_mode()
    all_passed &= test_export_target()
    all_passed &= test_task_status()
    all_passed &= test_transcript_segment()
    all_passed &= test_export_result()
    all_passed &= test_export_context()
    all_passed &= test_app_config()
    all_passed &= test_ai_config()
    all_passed &= test_download_config()
    
    print("\n" + "=" * 50)
    if all_passed:
        print("✓ 所有测试通过")
    else:
        print("✗ 部分测试失败")
    print("=" * 50)
