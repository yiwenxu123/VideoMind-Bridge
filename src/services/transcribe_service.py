"""转录服务实现 - 基于 faster-whisper"""

import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel

from ..models.task import TranscriptSegment
from ..utils import get_logger
from ..utils.exceptions import TranscribeError

logger = get_logger(__name__)

ProgressCallback = Callable[[str, float], None]


@dataclass
class TranscriptResult:
    """转录结果"""
    segments: list[TranscriptSegment]
    language: str
    language_probability: float
    full_text: str
    formatted_text: str  # 带时间戳的格式


class ModelCache:
    """
    Whisper 模型缓存管理器
    
    使用 LRU (Least Recently Used) 策略管理模型缓存，
    防止内存无限增长。
    """

    MAX_CACHE_SIZE = 2  # 最多缓存 2 个模型

    def __init__(self, max_size: int = 2):
        self._cache: OrderedDict[str, WhisperModel] = OrderedDict()
        self._lock = threading.Lock()
        self._max_size = max_size

    def get(self, model_size: str) -> WhisperModel:
        """
        获取模型（如果不存在则加载）
        
        使用 LRU 策略：访问时移动到末尾，淘汰最旧的
        """
        with self._lock:
            if model_size in self._cache:
                self._cache.move_to_end(model_size)
                logger.debug(f"模型 {model_size} 命中缓存")
                return self._cache[model_size]

            if len(self._cache) >= self._max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                logger.info(f"缓存已满，移除最旧的模型: {oldest_key}")

            model = self._load_model(model_size)
            self._cache[model_size] = model
            return model

    def _load_model(self, model_size: str) -> WhisperModel:
        """加载模型"""
        logger.info(f"加载 Whisper {model_size} 模型...")

        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

        device = "auto"
        compute_type = "int8"

        model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=str(Path.home() / ".cache" / "whisper")
        )

        logger.info(f"Whisper {model_size} 模型已加载")
        return model

    def clear(self) -> int:
        """清空缓存，返回清理的模型数量"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"已清理 {count} 个缓存的 Whisper 模型")
            return count

    def get_cached_sizes(self) -> list[str]:
        """获取已缓存的模型大小列表"""
        with self._lock:
            return list(self._cache.keys())

    @property
    def size(self) -> int:
        """当前缓存大小"""
        with self._lock:
            return len(self._cache)


_model_cache: ModelCache | None = None
_model_cache_lock = threading.Lock()


def _get_model_cache() -> ModelCache:
    """获取全局模型缓存实例"""
    global _model_cache
    if _model_cache is None:
        with _model_cache_lock:
            if _model_cache is None:
                _model_cache = ModelCache()
    return _model_cache


def _get_cached_model(model_size: str) -> WhisperModel:
    """获取缓存的模型（线程安全）"""
    return _get_model_cache().get(model_size)


def clear_model_cache() -> int:
    """清理模型缓存（释放内存），返回清理的模型数量"""
    return _get_model_cache().clear()


def get_cached_model_sizes() -> list[str]:
    """获取已缓存的模型大小列表"""
    return _get_model_cache().get_cached_sizes()


class TranscribeService:
    """语音转录服务 - 基于 faster-whisper"""

    SUPPORTED_MODELS = ["tiny", "base", "small", "medium", "large"]

    # 重试配置
    MAX_RETRIES = 2
    RETRY_DELAY = 1.0  # 初始延迟（秒）
    RETRY_BACKOFF = 2.0  # 退避系数

    def __init__(self, model_size: str = "small"):
        if model_size not in self.SUPPORTED_MODELS:
            raise ValueError(f"不支持的模型: {model_size}，可选: {self.SUPPORTED_MODELS}")

        self.model_size = model_size
        self._model: WhisperModel | None = None

    def _load_model(self, progress_callback: ProgressCallback | None = None) -> None:
        """懒加载模型（使用全局缓存）"""
        if self._model is not None:
            return

        if progress_callback:
            progress_callback(f"加载 Whisper {self.model_size} 模型...", 0)

        # 使用全局缓存获取模型
        self._model = _get_cached_model(self.model_size)

        if progress_callback:
            progress_callback(f"Whisper {self.model_size} 模型加载完成", 10)

    def transcribe(
        self,
        audio_path: Path,
        language: str | None = "zh",
        progress_callback: ProgressCallback | None = None
    ) -> TranscriptResult:
        """
        转录音频（带重试机制）

        Args:
            audio_path: 音频文件路径
            language: 语言代码，None 表示自动检测
            progress_callback: 进度回调

        Returns:
            TranscriptResult: 转录结果

        Raises:
            TranscribeError: 转录失败时抛出
        """
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                return self._do_transcribe(audio_path, language, progress_callback)
            except (IndexError, RuntimeError) as e:
                last_error = e
                error_msg = str(e)

                # 某些错误不需要重试
                if "不支持的模型" in error_msg or "音频文件不存在" in error_msg:
                    raise TranscribeError(
                        error_msg,
                        error_code="TRANSCRIBE_FAILED",
                        details={"audio_path": str(audio_path)}
                    ) from e

                # 其他错误可以重试
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAY * (self.RETRY_BACKOFF ** attempt)
                    logger.warning(f"转录失败（尝试 {attempt + 1}/{self.MAX_RETRIES}）: {e}，{delay:.1f}秒后重试...")
                    if progress_callback:
                        progress_callback(f"转录失败，{delay:.1f}秒后重试...", 0)
                    time.sleep(delay)
                else:
                    logger.error(f"转录失败，已重试 {self.MAX_RETRIES} 次: {e}")

        # 所有重试都失败了
        raise TranscribeError(
            f"转录失败，已重试 {self.MAX_RETRIES} 次: {last_error}",
            error_code="TRANSCRIBE_FAILED",
            details={
                "audio_path": str(audio_path),
                "retries": self.MAX_RETRIES,
                "model": self.model_size
            }
        ) from last_error

    def _do_transcribe(
        self,
        audio_path: Path,
        language: str | None = "zh",
        progress_callback: ProgressCallback | None = None
    ) -> TranscriptResult:
        """
        实际执行转录（内部方法）

        Args:
            audio_path: 音频文件路径
            language: 语言代码，None 表示自动检测
            progress_callback: 进度回调

        Returns:
            TranscriptResult: 转录结果
        """
        # 检查音频文件
        if not audio_path.exists():
            raise TranscribeError(
                f"音频文件不存在: {audio_path}",
                error_code="AUDIO_EXTRACTION_FAILED",
                details={"audio_path": str(audio_path)}
            )

        # 加载模型
        try:
            self._load_model(progress_callback)
        except Exception as e:
            raise TranscribeError(
                f"模型加载失败: {e}",
                error_code="MODEL_LOAD_FAILED",
                details={"model": self.model_size}
            ) from e

        if progress_callback:
            progress_callback("开始转录...", 15)

        # 执行转录
        assert self._model is not None  # 确保模型已加载
        try:
            segments_iter, info = self._model.transcribe(
                str(audio_path),
                language=language,
                beam_size=5,
                best_of=5,
                condition_on_previous_text=True,
            )
        except IndexError as e:
            # 处理 faster-whisper 的索引错误（通常是音频文件问题）
            raise TranscribeError(
                "音频文件处理失败，可能是格式不支持或文件损坏。请尝试安装 ffmpeg: brew install ffmpeg",
                error_code="AUDIO_EXTRACTION_FAILED",
                details={"audio_path": str(audio_path)}
            ) from e
        except Exception as e:
            raise TranscribeError(
                f"转录过程中发生错误: {e}",
                error_code="TRANSCRIBE_FAILED",
                details={"audio_path": str(audio_path)}
            ) from e

        if progress_callback:
            progress_callback(f"检测到语言: {info.language} ({info.language_probability:.0%})", 20)

        # 收集结果
        segments: list[TranscriptSegment] = []
        full_text_parts: list[str] = []
        formatted_parts: list[str] = []

        segment_list = list(segments_iter)
        total_segments = len(segment_list)

        for i, segment in enumerate(segment_list):
            seg = TranscriptSegment(
                start=segment.start,
                end=segment.end,
                text=segment.text.strip()
            )
            segments.append(seg)
            full_text_parts.append(segment.text.strip())

            # 带时间戳的格式
            timestamp = self._format_time(segment.start)
            formatted_parts.append(f"[{timestamp}] {segment.text.strip()}")

            # 进度回调
            if progress_callback and total_segments > 0:
                progress_percent = 20 + (i + 1) / total_segments * 75
                progress_callback(f"转录中... {i+1}/{total_segments}", progress_percent)

        if progress_callback:
            progress_callback("转录完成", 100)

        return TranscriptResult(
            segments=segments,
            language=info.language,
            language_probability=info.language_probability,
            full_text="\n".join(full_text_parts),
            formatted_text="\n".join(formatted_parts)
        )

    @staticmethod
    def _format_time(seconds: float) -> str:
        """格式化为时间字符串 HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def get_available_models(self) -> list[str]:
        """获取可用模型列表"""
        return self.SUPPORTED_MODELS.copy()


# 测试代码
if __name__ == "__main__":
    def print_progress(status: str, percent: float):
        print(f"[{percent:5.1f}%] {status}")

    # 测试 tiny 模型速度
    print("=== 测试 tiny 模型 ===")
    service = TranscribeService("tiny")

    test_audio = Path("./output/RPA失去王座，微软Playwright MCP重新定义浏览器.m4a")
    if test_audio.exists():
        import time
        start = time.time()

        result = service.transcribe(test_audio, progress_callback=print_progress)

        elapsed = time.time() - start
        print(f"\n转录完成! 耗时: {elapsed:.1f}秒")
        print(f"语言: {result.language} ({result.language_probability:.1%})")
        print(f"片段数: {len(result.segments)}")
        print("\n前3条转录:")
        for seg in result.segments[:3]:
            print(f"[{service._format_time(seg.start)}] {seg.text}")
    else:
        print(f"测试音频不存在: {test_audio}")
