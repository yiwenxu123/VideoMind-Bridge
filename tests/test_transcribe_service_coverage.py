"""覆盖 transcribe_service.py 缺失路径的测试"""
from pathlib import Path
from unittest import mock

import pytest

from src.services.transcribe_service import (
    ModelCache,
    TranscribeService,
    clear_model_cache,
    get_cached_model_sizes,
)
from src.utils.exceptions import TranscribeError


class TestModelCacheLRU:
    """ModelCache LRU 行为测试"""

    def test_cache_hit_moves_to_end(self):
        cache = ModelCache(max_size=3)
        m1, m2, m3 = mock.MagicMock(), mock.MagicMock(), mock.MagicMock()
        cache._cache["tiny"] = m1
        cache._cache["base"] = m2
        cache._cache["small"] = m3
        cache._cache.move_to_end = mock.MagicMock()

        with mock.patch.object(cache, "_load_model"):
            cache.get("tiny")

        cache._cache.move_to_end.assert_called_once_with("tiny")

    def test_cache_eviction_when_full(self):
        cache = ModelCache(max_size=2)
        m1, m2 = mock.MagicMock(), mock.MagicMock()
        cache._cache["tiny"] = m1
        cache._cache["base"] = m2

        with mock.patch.object(cache, "_load_model", return_value=mock.MagicMock()):
            cache.get("small")

        assert "tiny" not in cache._cache
        assert len(cache._cache) == 2

    def test_cache_eviction_removes_oldest(self):
        cache = ModelCache(max_size=1)
        m1 = mock.MagicMock()
        cache._cache["tiny"] = m1

        with mock.patch.object(cache, "_load_model", return_value=mock.MagicMock()):
            cache.get("base")

        assert "tiny" not in cache._cache
        assert "base" in cache._cache


class TestModelCacheUtils:
    """ModelCache 工具方法测试"""

    def test_clear_returns_count(self):
        cache = ModelCache(max_size=3)
        cache._cache["tiny"] = mock.MagicMock()
        cache._cache["base"] = mock.MagicMock()
        assert cache.clear() == 2
        assert cache.size == 0

    def test_clear_empty_cache(self):
        cache = ModelCache()
        assert cache.clear() == 0

    def test_get_cached_sizes(self):
        cache = ModelCache(max_size=3)
        cache._cache["tiny"] = mock.MagicMock()
        cache._cache["base"] = mock.MagicMock()
        assert cache.get_cached_sizes() == ["tiny", "base"]

    def test_get_cached_sizes_empty(self):
        cache = ModelCache()
        assert cache.get_cached_sizes() == []

    def test_size_property(self):
        cache = ModelCache()
        assert cache.size == 0
        cache._cache["tiny"] = mock.MagicMock()
        assert cache.size == 1


class TestGlobalCacheFunctions:
    """全局缓存函数测试"""

    def test_clear_model_cache(self):
        with mock.patch("src.services.transcribe_service._get_model_cache") as mock_get:
            mock_cache = mock.MagicMock()
            mock_cache.clear.return_value = 2
            mock_get.return_value = mock_cache
            assert clear_model_cache() == 2

    def test_get_cached_model_sizes(self):
        with mock.patch("src.services.transcribe_service._get_model_cache") as mock_get:
            mock_cache = mock.MagicMock()
            mock_cache.get_cached_sizes.return_value = ["tiny"]
            mock_get.return_value = mock_cache
            assert get_cached_model_sizes() == ["tiny"]


class TestTranscribeServiceLoadModel:
    """_load_model 路径测试"""

    def test_load_model_early_return_when_already_loaded(self):
        service = TranscribeService("tiny")
        service._model = mock.MagicMock()
        with mock.patch("src.services.transcribe_service._get_cached_model") as mock_cached:
            service._load_model()
            mock_cached.assert_not_called()

    def test_load_model_with_callback(self):
        service = TranscribeService("tiny")
        callback = mock.MagicMock()
        with mock.patch("src.services.transcribe_service._get_cached_model", return_value=mock.MagicMock()):
            service._load_model(progress_callback=callback)
        assert callback.call_count == 2

    def test_load_model_without_callback(self):
        service = TranscribeService("tiny")
        with mock.patch("src.services.transcribe_service._get_cached_model", return_value=mock.MagicMock()):
            service._load_model()
        assert service._model is not None


class TestTranscribeServiceTranscribe:
    """transcribe 方法重试和错误路径"""

    def test_transcribe_all_retries_fail(self):
        service = TranscribeService("tiny")
        with mock.patch.object(
            service, "_do_transcribe",
            side_effect=TranscribeError("GPU out of memory", error_code="TRANSCRIBE_FAILED"),
        ):
            with pytest.raises(TranscribeError) as excinfo:
                service.transcribe(Path("/fake/audio.wav"))
            assert "重试" in str(excinfo.value)

    def test_transcribe_retry_then_succeed(self):
        service = TranscribeService("tiny")
        fake_result = mock.MagicMock()
        with mock.patch.object(
            service, "_do_transcribe",
            side_effect=[TranscribeError("transient", error_code="TRANSCRIBE_FAILED"), fake_result],
        ):
            result = service.transcribe(Path("/fake/audio.wav"))
            assert result is fake_result

    def test_transcribe_non_retryable_error(self):
        service = TranscribeService("tiny")
        with mock.patch.object(
            service, "_do_transcribe",
            side_effect=TranscribeError("不支持的模型", error_code="LANGUAGE_NOT_SUPPORTED"),
        ):
            with pytest.raises(Exception) as excinfo:
                service.transcribe(Path("/fake/audio.wav"))
            assert "不支持的模型" in str(excinfo.value)

    def test_transcribe_audio_not_found_non_retryable(self):
        service = TranscribeService("tiny")
        with mock.patch.object(
            service, "_do_transcribe",
            side_effect=TranscribeError("音频文件不存在", error_code="AUDIO_EXTRACTION_FAILED"),
        ):
            with pytest.raises(Exception) as excinfo:
                service.transcribe(Path("/fake/audio.wav"))
            assert "音频文件不存在" in str(excinfo.value)

    def test_transcribe_progress_callback_on_retry(self):
        service = TranscribeService("tiny")
        callback = mock.MagicMock()
        with mock.patch.object(
            service, "_do_transcribe",
            side_effect=[TranscribeError("transient", error_code="TRANSCRIBE_FAILED"), mock.MagicMock()],
        ):
            service.transcribe(Path("/fake/audio.wav"), progress_callback=callback)
        retry_call = [c for c in callback.call_args_list if "重试" in str(c)]
        assert len(retry_call) > 0


class TestTranscribeServiceDoTranscribe:
    """_do_transcribe 错误路径"""

    @pytest.fixture
    def audio_path(self, tmp_path) -> Path:
        p = tmp_path / "audio.wav"
        p.write_text("fake audio data")
        return p

    def test_do_transcribe_audio_not_exists(self):
        service = TranscribeService("tiny")
        with pytest.raises(Exception) as excinfo:
            service._do_transcribe(Path("/nonexistent/audio.wav"))
        assert "不存在" in str(excinfo.value)

    def test_do_transcribe_model_load_failure(self, audio_path):
        service = TranscribeService("tiny")
        with mock.patch.object(service, "_load_model", side_effect=Exception("model crashed")):
            with pytest.raises(Exception) as excinfo:
                service._do_transcribe(audio_path)
            assert "模型加载失败" in str(excinfo.value)

    def test_do_transcribe_with_callback(self, audio_path):
        service = TranscribeService("tiny")
        service._model = mock.MagicMock()
        mock_info = mock.MagicMock(language="zh", language_probability=0.95)
        service._model.transcribe.return_value = ([], mock_info)
        callback = mock.MagicMock()
        service._do_transcribe(audio_path, progress_callback=callback)
        assert callback.called

    def test_do_transcribe_index_error(self, audio_path):
        service = TranscribeService("tiny")
        service._model = mock.MagicMock()
        service._model.transcribe.side_effect = IndexError("list index out of range")
        with pytest.raises(Exception) as excinfo:
            service._do_transcribe(audio_path)
        assert "ffmpeg" in str(excinfo.value)

    def test_do_transcribe_generic_error(self, audio_path):
        service = TranscribeService("tiny")
        service._model = mock.MagicMock()
        service._model.transcribe.side_effect = ValueError("some error")
        with pytest.raises(Exception) as excinfo:
            service._do_transcribe(audio_path)
        assert "转录过程中发生错误" in str(excinfo.value)


class TestTranscribeServiceFormatTime:
    """_format_time 测试"""

    @pytest.mark.parametrize("seconds,expected", [
        (0, "00:00:00"),
        (1, "00:00:01"),
        (59, "00:00:59"),
        (60, "00:01:00"),
        (3661, "01:01:01"),
        (86399, "23:59:59"),
    ])
    def test_format_time(self, seconds, expected):
        assert TranscribeService._format_time(seconds) == expected


class TestTranscribeServiceGetAvailableModels:
    """get_available_models 测试"""

    def test_returns_copy_of_supported_models(self):
        service = TranscribeService("tiny")
        models = service.get_available_models()
        assert models == ["tiny", "base", "small", "medium", "large"]
        models.append("extra")
        assert "extra" not in service.SUPPORTED_MODELS


class TestTranscribeServiceInit:
    """初始化测试"""

    def test_invalid_model_raises(self):
        with pytest.raises(ValueError):
            TranscribeService("invalid_model")


class TestDoubleCheckedLocking:
    """_get_model_cache 双检锁测试"""

    def test_second_null_check_path(self):
        import src.services.transcribe_service as ts

        saved = ts._model_cache
        ts._model_cache = None
        try:
            with mock.patch.object(ts, "ModelCache") as MockModelCache:
                MockModelCache.return_value = mock.sentinel.cache
                cache1 = ts._get_model_cache()
                cache2 = ts._get_model_cache()
                assert cache1 is cache2
                assert MockModelCache.call_count == 1
        finally:
            ts._model_cache = saved
