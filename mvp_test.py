#!/usr/bin/env python3
"""
VideoMind Bridge - MVP 技术验证脚本
策略：统一使用本地 Whisper 转录，避免登录复杂度，保证一致性体验
流程：下载音频 → Whisper 转录 → 输出 SRT
"""

import os
import sys
import time
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass

import yt_dlp
from faster_whisper import WhisperModel


# ============ 配置 ============
TEST_VIDEO_URL = "https://www.bilibili.com/video/BV19NpFzbETP/"
WHISPER_MODEL = "small"  # 推荐: small(平衡) 或 medium(高质量)
WHISPER_LANGUAGE = "zh"  # zh(中文), en(英文), 或 None(自动检测)
OUTPUT_DIR = Path(__file__).parent / "output"


class Colors:
    """终端颜色"""
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    END = "\033[0m"


def log_step(step: str, message: str):
    """打印步骤日志"""
    timestamp = time.strftime("%H:%M:%S")
    print(f"{Colors.CYAN}[{timestamp}] {Colors.YELLOW}[{step}]{Colors.END} {message}")


def log_success(message: str):
    """打印成功日志"""
    print(f"{Colors.GREEN}✓ {message}{Colors.END}")


def log_error(message: str):
    """打印错误日志"""
    print(f"{Colors.RED}✗ {message}{Colors.END}")


def log_info(message: str):
    """打印信息日志"""
    print(f"{Colors.BLUE}ℹ {message}{Colors.END}")


@dataclass
class TranscriptSegment:
    """转录片段"""
    start: float
    end: float
    text: str


class VideoProcessor:
    """
    视频处理器 - 统一使用 Whisper 本地转录
    策略：避免平台字幕登录复杂度，保证一致性体验
    """

    def __init__(
        self,
        output_dir: Path,
        model_size: str = "small",
        language: Optional[str] = "zh"
    ):
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True)
        self.model_size = model_size
        self.language = language
        self._whisper_model: Optional[WhisperModel] = None

    def _get_whisper_model(self) -> WhisperModel:
        """懒加载 Whisper 模型"""
        if self._whisper_model is None:
            log_step("模型", f"加载 Whisper 模型: {self.model_size}")

            # 设置 HuggingFace 镜像源（国内加速）
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

            # Apple Silicon 使用 Metal 加速
            device = "auto"  # auto 会自动检测 Metal
            compute_type = "int8"

            self._whisper_model = WhisperModel(
                self.model_size,
                device=device,
                compute_type=compute_type,
                download_root=str(Path.home() / ".cache" / "whisper")
            )
            log_success(f"Whisper 模型加载完成 ({self.model_size})")

        return self._whisper_model

    def download_audio(self, url: str) -> Optional[Path]:
        """
        下载视频音频
        直接下载原始格式，无需 ffmpeg 转换
        """
        log_step("下载", f"开始处理: {url}")

        output_template = str(self.output_dir / "%(title)s.%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": [],  # 禁用 ffmpeg 后处理
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # 获取信息
                info = ydl.extract_info(url, download=False)
                title = info.get("title", "unknown")
                duration = info.get("duration", 0)
                uploader = info.get("uploader", "unknown")

                log_info(f"标题: {title}")
                log_info(f"UP主: {uploader}")
                log_info(f"时长: {duration // 60}分{duration % 60}秒")

                # 下载
                log_step("下载", "下载音频中...")
                ydl.download([url])

                # 查找下载的文件
                audio_extensions = [".m4a", ".webm", ".opus", ".mp3", ".ogg"]
                for ext in audio_extensions:
                    audio_file = self.output_dir / f"{title}{ext}"
                    if audio_file.exists():
                        log_success(f"音频下载完成: {audio_file.name}")
                        return audio_file

                    # 模糊匹配
                    files = list(self.output_dir.glob(f"*{ext}"))
                    if files:
                        log_success(f"音频下载完成: {files[0].name}")
                        return files[0]

                log_error("未找到下载的音频文件")
                return None

        except Exception as e:
            log_error(f"下载失败: {e}")
            return None

    def transcribe_audio(
        self,
        audio_path: Path,
        output_name: Optional[str] = None
    ) -> Tuple[Optional[Path], List[TranscriptSegment]]:
        """
        使用 Whisper 转录音频
        统一转录策略：本地模型，无需登录，体验一致
        """
        log_step("转录", f"开始转录: {audio_path.name}")

        try:
            model = self._get_whisper_model()

            # 执行转录
            segments_iter, info = model.transcribe(
                str(audio_path),
                language=self.language,  # 指定语言或自动检测
                beam_size=5,
                best_of=5,
                condition_on_previous_text=True,
            )

            log_info(f"检测到语言: {info.language} (置信度: {info.language_probability:.1%})")

            # 收集转录结果
            segments: List[TranscriptSegment] = []
            srt_lines: List[str] = []

            for i, segment in enumerate(segments_iter, start=1):
                # 保存片段数据
                seg = TranscriptSegment(
                    start=segment.start,
                    end=segment.end,
                    text=segment.text.strip()
                )
                segments.append(seg)

                # 生成 SRT 格式
                srt_lines.append(f"{i}")
                srt_lines.append(f"{self._format_time(segment.start)} --> {self._format_time(segment.end)}")
                srt_lines.append(segment.text.strip())
                srt_lines.append("")

            # 保存 SRT 文件
            srt_name = output_name or audio_path.stem
            srt_path = self.output_dir / f"{srt_name}.srt"
            srt_path.write_text("\n".join(srt_lines), encoding="utf-8")

            log_success(f"转录完成: {srt_path.name}")
            log_info(f"共 {len(segments)} 个片段")

            return srt_path, segments

        except Exception as e:
            log_error(f"转录失败: {e}")
            return None, []

    @staticmethod
    def _format_time(seconds: float) -> str:
        """格式化为 SRT 时间格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def process(self, url: str) -> Optional[Path]:
        """
        统一处理流程：下载 → 转录
        策略：始终使用本地 Whisper，不依赖平台字幕
        """
        total_start = time.time()

        # 步骤 1: 下载音频
        download_start = time.time()
        audio_path = self.download_audio(url)
        download_time = time.time() - download_start

        if not audio_path:
            return None

        log_info(f"下载耗时: {download_time:.1f}秒")
        print()

        # 步骤 2: Whisper 转录（统一策略）
        transcribe_start = time.time()
        srt_path, segments = self.transcribe_audio(audio_path)
        transcribe_time = time.time() - transcribe_start

        if not srt_path:
            return None

        log_info(f"转录耗时: {transcribe_time:.1f}秒")
        print()

        # 完成统计
        total_time = time.time() - total_start

        print(f"\n{Colors.GREEN}{'='*60}{Colors.END}")
        print(f"{Colors.GREEN}  ✅ 处理完成！{Colors.END}")
        print(f"{Colors.GREEN}{'='*60}{Colors.END}\n")

        log_info(f"音频: {audio_path.name}")
        log_info(f"字幕: {srt_path.name}")
        print()
        log_info(f"下载: {download_time:.1f}s | 转录: {transcribe_time:.1f}s | 总计: {total_time:.1f}s")
        print()

        # 预览前3条
        print(f"{Colors.CYAN}字幕预览:{Colors.END}")
        for seg in segments[:3]:
            print(f"[{self._format_time(seg.start)}] {seg.text}")
        if len(segments) > 3:
            print(f"... 共 {len(segments)} 条")
        print()

        return srt_path


def main():
    """主入口"""
    print(f"\n{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.CYAN}  VideoMind Bridge - MVP 验证{Colors.END}")
    print(f"{Colors.CYAN}  策略：统一 Whisper 本地转录{Colors.END}")
    print(f"{Colors.CYAN}{'='*60}{Colors.END}\n")

    log_info(f"Python: {sys.version.split()[0]}")
    log_info(f"模型: {WHISPER_MODEL}")
    log_info(f"语言: {WHISPER_LANGUAGE or '自动检测'}")
    print()

    # 创建处理器并执行
    processor = VideoProcessor(
        output_dir=OUTPUT_DIR,
        model_size=WHISPER_MODEL,
        language=WHISPER_LANGUAGE
    )

    result = processor.process(TEST_VIDEO_URL)

    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
