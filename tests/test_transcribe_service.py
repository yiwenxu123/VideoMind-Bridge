"""转录服务测试 - Mock 模式"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import threading
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.transcribe_service import (
    TranscribeService,
    TranscriptSegment,
    TranscriptResult,
    ModelCache,
)
from src.utils.exceptions import TranscribeError


class TestTranscriptSegment:
    """转录片段测试"""
    
    def test_segment_creation(self):
        """测试片段创建"""
        segment = TranscriptSegment(
            start=0.0,
            end=5.5,
            text="这是测试文本"
        )
        
        assert segment.start == 0.0
        assert segment.end == 5.5
        assert segment.text == "这是测试文本"
    
    def test_segment_duration(self):
        """测试片段时长计算"""
        segment = TranscriptSegment(
            start=10.0,
            end=25.5,
            text="测试"
        )
        
        duration = segment.end - segment.start
        assert duration == 15.5


class TestTranscriptResult:
    """转录结果测试"""
    
    def test_result_creation(self):
        """测试结果创建"""
        segments = [
            TranscriptSegment(start=0.0, end=5.0, text="第一段"),
            TranscriptSegment(start=5.0, end=10.0, text="第二段"),
        ]
        
        result = TranscriptResult(
            segments=segments,
            language="zh",
            language_probability=0.95,
            full_text="第一段第二段",
            formatted_text="[00:00:00] 第一段\n[00:00:05] 第二段"
        )
        
        assert len(result.segments) == 2
        assert result.language == "zh"
        assert result.language_probability == 0.95
        assert result.full_text == "第一段第二段"
    
    def test_result_empty_segments(self):
        """测试空片段结果"""
        result = TranscriptResult(
            segments=[],
            language="auto",
            language_probability=0.0,
            full_text="",
            formatted_text=""
        )
        
        assert len(result.segments) == 0
        assert result.full_text == ""


class TestModelCache:
    """模型缓存测试"""
    
    def test_cache_initialization(self):
        """测试缓存初始化"""
        cache = ModelCache(max_size=2)
        
        assert cache.size == 0
        assert cache._max_size == 2
        assert len(cache.get_cached_sizes()) == 0
    
    def test_cache_max_size(self):
        """测试缓存最大大小限制"""
        cache = ModelCache(max_size=2)
        
        assert cache._max_size == 2
        assert cache.MAX_CACHE_SIZE == 2
    
    def test_cache_clear(self):
        """测试缓存清理"""
        cache = ModelCache(max_size=2)
        
        count = cache.clear()
        
        assert count == 0
        assert cache.size == 0
    
    def test_cache_thread_safety(self):
        """测试缓存线程安全"""
        cache = ModelCache(max_size=3)
        results = []
        
        def get_cached_sizes():
            results.append(cache.get_cached_sizes())
        
        threads = [threading.Thread(target=get_cached_sizes) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(results) == 5


class TestTranscribeServiceInit:
    """转录服务初始化测试"""
    
    def test_init_default_model(self):
        """测试默认模型初始化"""
        service = TranscribeService()
        
        assert service.model_size == "small"
    
    def test_init_custom_model(self):
        """测试自定义模型初始化"""
        service = TranscribeService(model_size="base")
        
        assert service.model_size == "base"
    
    def test_init_invalid_model(self):
        """测试无效模型初始化"""
        with pytest.raises(ValueError) as exc_info:
            TranscribeService(model_size="invalid_model")
        
        assert "不支持的模型" in str(exc_info.value)
    
    def test_supported_models(self):
        """测试支持的模型列表"""
        supported = TranscribeService.SUPPORTED_MODELS
        
        assert "tiny" in supported
        assert "base" in supported
        assert "small" in supported
        assert "medium" in supported
        assert "large" in supported


class TestTranscribeServiceMock:
    """转录服务 Mock 测试"""
    
    @patch('src.services.transcribe_service._get_cached_model')
    def test_transcribe_success(self, mock_get_model, tmp_path):
        """测试转录成功"""
        mock_model = MagicMock()
        mock_get_model.return_value = mock_model
        
        mock_segment = MagicMock()
        mock_segment.start = 0.0
        mock_segment.end = 5.0
        mock_segment.text = "测试文本"
        
        mock_info = MagicMock()
        mock_info.language = "zh"
        mock_info.language_probability = 0.95
        
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake audio data")
        
        service = TranscribeService(model_size="tiny")
        service._model = mock_model
        
        assert service._model is not None
    
    def test_transcribe_error_handling(self, tmp_path):
        """测试转录错误处理"""
        error = TranscribeError(
            "转录失败",
            error_code="TRANSCRIBE_FAILED",
            details={"audio_path": str(tmp_path / "test.wav")}
        )
        
        assert error.error_code == "TRANSCRIBE_FAILED"
        assert "转录失败" in error.message


class TestTranscribeError:
    """转录错误测试"""
    
    def test_transcribe_error_creation(self):
        """测试转录错误创建"""
        error = TranscribeError(
            "音频提取失败",
            error_code="AUDIO_EXTRACTION_FAILED",
            details={"file": "test.mp4"}
        )
        
        assert error.error_code == "AUDIO_EXTRACTION_FAILED"
        assert error.message == "音频提取失败"
        assert error.details["file"] == "test.mp4"
    
    def test_model_load_error(self):
        """测试模型加载错误"""
        error = TranscribeError(
            "转录模型加载失败",
            error_code="MODEL_LOAD_FAILED",
            details={"model": "large"}
        )
        
        assert error.error_code == "MODEL_LOAD_FAILED"
    
    def test_audio_too_short_error(self):
        """测试音频太短错误"""
        error = TranscribeError(
            "音频太短，无法转录",
            error_code="AUDIO_TOO_SHORT",
            details={"duration": 0.5}
        )
        
        assert error.error_code == "AUDIO_TOO_SHORT"


class TestProgressCallback:
    """进度回调测试"""
    
    def test_progress_callback_called(self):
        """测试进度回调被调用"""
        progress_values = []
        
        def callback(message: str, progress: float):
            progress_values.append((message, progress))
        
        callback("开始处理", 0.0)
        callback("处理中", 50.0)
        callback("完成", 100.0)
        
        assert len(progress_values) == 3
        assert progress_values[0] == ("开始处理", 0.0)
        assert progress_values[2] == ("完成", 100.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
