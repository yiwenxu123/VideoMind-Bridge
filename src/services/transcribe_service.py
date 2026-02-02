"""转录服务实现 - 基于 faster-whisper"""

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from faster_whisper import WhisperModel

from ..utils import get_logger
from ..utils.exceptions import TranscribeError

logger = get_logger(__name__)

ProgressCallback = Callable[[str, float], None]


@dataclass
class TranscriptSegment:
    """转录片段"""
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    """转录结果"""
    segments: List[TranscriptSegment]
    language: str
    language_probability: float
    full_text: str
    formatted_text: str  # 带时间戳的格式


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
        self._model: Optional[WhisperModel] = None

    def _load_model(self, progress_callback: Optional[ProgressCallback] = None):
        """懒加载模型"""
        if self._model is not None:
            return

        if progress_callback:
            progress_callback(f"加载 Whisper {self.model_size} 模型...", 0)

        # 设置 HuggingFace 镜像源（国内加速）
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

        # Apple Silicon 使用 Metal 加速
        device = "auto"
        compute_type = "int8"

        self._model = WhisperModel(
            self.model_size,
            device=device,
            compute_type=compute_type,
            download_root=str(Path.home() / ".cache" / "whisper")
        )

        if progress_callback:
            progress_callback(f"Whisper {self.model_size} 模型加载完成", 10)

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = "zh",
        progress_callback: Optional[ProgressCallback] = None
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
        language: Optional[str] = "zh",
        progress_callback: Optional[ProgressCallback] = None
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
                f"音频文件处理失败，可能是格式不支持或文件损坏。请尝试安装 ffmpeg: brew install ffmpeg",
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
        segments: List[TranscriptSegment] = []
        full_text_parts: List[str] = []
        formatted_parts: List[str] = []

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

    def get_available_models(self) -> List[str]:
        """获取可用模型列表"""
        return self.SUPPORTED_MODELS.copy()


# 测试代码
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

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
