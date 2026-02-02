"""下载服务实现 - 基于 yt-dlp"""

import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlparse

import yt_dlp

from ..models.task import VideoMetadata
from ..utils import get_logger, sanitize_filename
from ..utils.exceptions import DownloadError, NetworkError

logger = get_logger(__name__)

ProgressCallback = Callable[[str, float], None]


@dataclass
class DownloadResult:
    """下载结果"""
    video_path: Optional[Path]  # 视频文件路径（如果下载了视频）
    audio_path: Path            # 音频文件路径（用于转录）
    metadata: VideoMetadata


class DownloadService:
    """视频下载服务 - 使用 yt-dlp Python API"""

    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # 初始延迟（秒）
    RETRY_BACKOFF = 2.0  # 退避系数

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def download(
        self,
        url: str,
        download_video: bool = True,
        video_quality: str = "best",
        progress_callback: Optional[ProgressCallback] = None
    ) -> DownloadResult:
        """
        下载视频和/或音频（带重试机制）

        Args:
            url: 视频链接
            download_video: True 时下载完整视频，False 时仅下载音频
            video_quality: 视频质量 (best/worst/720p/1080p等)
            progress_callback: 进度回调函数 (status, percent) -> None

        Returns:
            DownloadResult: 下载结果

        Raises:
            DownloadError: 下载失败时抛出
        """
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                return self._do_download(url, download_video, video_quality, progress_callback)
            except (subprocess.CalledProcessError, yt_dlp.utils.DownloadError) as e:
                last_error = e
                error_msg = str(e)

                # 判断错误类型
                if "HTTP Error 404" in error_msg or "Video unavailable" in error_msg:
                    # 视频不存在，不需要重试
                    raise DownloadError(
                        f"视频不存在或已被删除: {error_msg}",
                        error_code="VIDEO_NOT_FOUND",
                        details={"url": url, "attempt": attempt + 1}
                    ) from e
                elif "Sign in to confirm your age" in error_msg:
                    # 年龄限制，不需要重试
                    raise DownloadError(
                        f"视频有年龄限制: {error_msg}",
                        error_code="AGE_RESTRICTED",
                        details={"url": url}
                    ) from e
                elif "This video is not available" in error_msg:
                    # 地区限制，不需要重试
                    raise DownloadError(
                        f"视频在您的地区不可用: {error_msg}",
                        error_code="REGION_BLOCKED",
                        details={"url": url}
                    ) from e

                # 其他错误可以重试
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAY * (self.RETRY_BACKOFF ** attempt)
                    logger.warning(f"下载失败（尝试 {attempt + 1}/{self.MAX_RETRIES}）: {e}，{delay:.1f}秒后重试...")
                    if progress_callback:
                        progress_callback(f"下载失败，{delay:.1f}秒后重试...", 0)
                    time.sleep(delay)
                else:
                    logger.error(f"下载失败，已重试 {self.MAX_RETRIES} 次: {e}")

        # 所有重试都失败了
        raise DownloadError(
            f"下载失败，已重试 {self.MAX_RETRIES} 次: {last_error}",
            error_code="DOWNLOAD_FAILED",
            details={"url": url, "retries": self.MAX_RETRIES}
        ) from last_error

    def _do_download(
        self,
        url: str,
        download_video: bool = True,
        video_quality: str = "best",
        progress_callback: Optional[ProgressCallback] = None
    ) -> DownloadResult:
        """
        实际执行下载（内部方法）

        Args:
            url: 视频链接
            download_video: True 时下载完整视频，False 时仅下载音频
            video_quality: 视频质量 (best/worst/720p/1080p等)
            progress_callback: 进度回调函数 (status, percent) -> None

        Returns:
            DownloadResult: 下载结果
        """
        # 使用简单的扁平化路径结构，避免嵌套目录导致的问题
        date_str = datetime.now().strftime("%Y-%m-%d")

        # 先获取视频标题，安全化处理
        try:
            with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                info = ydl.extract_info(url, download=False)
                raw_title = info.get("title", "unknown")
                safe_title = sanitize_filename(raw_title)
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"获取视频信息失败: {e}")
            raise DownloadError(
                f"无法获取视频信息: {e}",
                error_code="VIDEO_NOT_FOUND",
                details={"url": url}
            ) from e
        except Exception as e:
            logger.error(f"获取视频信息时发生未知错误: {e}")
            raise DownloadError(
                f"获取视频信息失败: {e}",
                error_code="DOWNLOAD_FAILED",
                details={"url": url}
            ) from e

        # 使用日期/标题结构组织文件
        # 注意：目录结构为 output_dir/date/title/title.ext
        output_dir = self.output_dir / date_str / safe_title
        output_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(output_dir / f"{safe_title}.%(ext)s")

        # 构建元数据（使用之前获取的 info）
        metadata = VideoMetadata(
            title=info.get("title", "unknown"),
            author=info.get("uploader", "unknown"),
            duration=info.get("duration", 0),
            platform=self._detect_platform(url),
            url=url,
            thumbnail_url=info.get("thumbnail"),
            description=info.get("description"),
        )

        if progress_callback:
            progress_callback(f"开始下载: {metadata.title}", 5)

        video_path: Optional[Path] = None
        audio_path: Path

        if download_video:
            # 模式 A: 下载视频 + 提取音频
            video_path, audio_path = self._download_video_and_audio(
                url, output_template, video_quality, progress_callback
            )
        else:
            # 模式 B: 仅下载音频
            audio_path = self._download_audio_only(
                url, output_template, progress_callback
            )

        if progress_callback:
            progress_callback("下载完成", 100)

        return DownloadResult(
            video_path=video_path,
            audio_path=audio_path,
            metadata=metadata
        )

    def _download_video_and_audio(
        self,
        url: str,
        output_template: str,
        quality: str,
        progress_callback: Optional[ProgressCallback]
    ) -> Tuple[Path, Path]:
        """下载视频（包含音频）和单独音频文件"""
        # 使用 subprocess 调用 yt-dlp 命令行工具，避免 Python API 在 GUI 中的问题
        import subprocess

        # 先获取视频信息
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title", "unknown")
            safe_title = sanitize_filename(title)

        # 构建输出路径 - 使用嵌套目录结构
        # output_dir/date/safe_title/video.%(ext)s
        output_path = Path(output_template)
        output_dir = output_path.parent
        # 确保目录存在
        output_dir.mkdir(parents=True, exist_ok=True)

        # 使用安全的输出模板 - 使用 video.%(ext)s 而不是标题
        # 这样可以避免 yt-dlp 处理特殊字符的问题
        safe_output_template = str(output_dir / "video.%(ext)s")

        # 根据质量参数构建格式选择器
        if quality == "best":
            format_spec = "bestvideo+bestaudio/best"
        elif quality == "worst":
            format_spec = "worstvideo+worstaudio/worst"
        elif quality.endswith("p"):
            height = quality.replace("p", "")
            format_spec = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        else:
            format_spec = "bestvideo+bestaudio/best"

        # 构建 yt-dlp 命令
        cmd = [
            "yt-dlp",
            "-o", safe_output_template,
            "-f", format_spec,
            "--merge-output-format", "mp4",
            "--no-warnings",
            "--progress",
            url
        ]

        if progress_callback:
            progress_callback(f"开始下载: {title}", 5)

        # 执行下载（使用 Popen 实时获取进度）
        error_output = []
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(output_dir.parent)
            )

            # 实时解析进度输出
            current_percent = 5.0
            for line in process.stdout:
                line = line.strip()
                logger.debug(f"yt-dlp: {line}")
                error_output.append(line)

                # 解析下载进度，如：[download]  45.3% of 9.30MiB at 6.70MiB/s ETA 00:00
                if "[download]" in line and "%" in line and "of" in line:
                    try:
                        # 提取百分比
                        percent_str = line.split("%")[0].split()[-1]
                        download_percent = float(percent_str)
                        # 映射到 5-60% 的范围
                        current_percent = 5.0 + (download_percent / 100.0) * 55.0
                        if progress_callback:
                            progress_callback(f"下载中... {download_percent:.1f}%", current_percent)
                    except (ValueError, IndexError):
                        pass
                elif "[Merger]" in line:
                    if progress_callback:
                        progress_callback("合并音视频...", 60.0)

            # 等待进程完成
            process.wait()
            if process.returncode != 0:
                # 收集错误信息
                error_msg = "\n".join(error_output[-10:])  # 最后10行
                raise subprocess.CalledProcessError(process.returncode, cmd, output=error_msg)

        except subprocess.CalledProcessError as e:
            logger.error(f"yt-dlp error: {e}")
            logger.error(f"yt-dlp output: {e.output}")
            raise RuntimeError(f"下载失败: {e.output or e}") from e

        # 查找下载的视频文件（现在应该是 video.mp4 或类似）
        video_path = self._find_file_in_dir(output_dir, [".mp4", ".webm", ".mkv", ".flv"])

        # 步骤2: 从视频提取音频（用于转录）
        if progress_callback:
            progress_callback("提取音频...", 65)

        audio_path = self._extract_audio_from_video(video_path, progress_callback)

        if progress_callback:
            progress_callback("音频提取完成", 95)

        return video_path, audio_path

    def _download_audio_only(
        self,
        url: str,
        output_template: str,
        progress_callback: Optional[ProgressCallback]
    ) -> Path:
        """仅下载音频"""
        import subprocess

        # 先获取视频信息
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title", "unknown")
            safe_title = sanitize_filename(title)

        # 构建输出路径
        output_path = Path(output_template.replace('%(ext)s', 'm4a'))
        output_dir = output_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        # 构建 yt-dlp 命令
        cmd = [
            "yt-dlp",
            "-o", str(output_path),
            "-f", "bestaudio/best",
            "-x",  # 提取音频
            "--audio-format", "m4a",
            "--no-warnings",
            "--progress",
            url
        ]

        if progress_callback:
            progress_callback(f"开始下载音频: {title}", 5)

        # 执行下载（使用 Popen 实时获取进度）
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(output_dir.parent)
            )

            # 实时解析进度输出
            for line in process.stdout:
                line = line.strip()
                logger.debug(f"yt-dlp: {line}")

                # 解析下载进度
                if "[download]" in line and "%" in line and "of" in line:
                    try:
                        percent_str = line.split("%")[0].split()[-1]
                        download_percent = float(percent_str)
                        # 映射到 5-95% 的范围
                        current_percent = 5.0 + (download_percent / 100.0) * 90.0
                        if progress_callback:
                            progress_callback(f"下载中... {download_percent:.1f}%", current_percent)
                    except (ValueError, IndexError):
                        pass
                elif "[ExtractAudio]" in line:
                    if progress_callback:
                        progress_callback("提取音频...", 95.0)

            # 等待进程完成
            process.wait()
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, cmd)

        except subprocess.CalledProcessError as e:
            logger.error(f"yt-dlp error: {e}")
            raise RuntimeError(f"下载失败: {e}") from e

        # 查找下载的音频文件
        return self._find_file(title, [".m4a", ".webm", ".opus", ".mp3", ".ogg"])

    def _extract_audio_from_video(
        self,
        video_path: Path,
        progress_callback: Optional[ProgressCallback] = None
    ) -> Path:
        """从视频提取音频（优先使用 ffmpeg，备选 pydub）"""
        # 使用 .wav 格式，兼容性更好
        audio_path = video_path.with_suffix(".wav")

        # 如果已存在，直接返回
        if audio_path.exists():
            return audio_path

        if progress_callback:
            progress_callback("提取音频...", 65)

        # 方法1: 使用 ffmpeg
        try:
            cmd = [
                "ffmpeg",
                "-i", str(video_path),
                "-vn",  # 禁用视频
                "-acodec", "pcm_s16le",  # PCM 16-bit 小端
                "-ar", "16000",  # 16kHz 采样率（Whisper 推荐）
                "-ac", "1",  # 单声道
                "-y",  # 覆盖已存在文件
                str(audio_path)
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            if audio_path.exists() and audio_path.stat().st_size > 0:
                logger.info(f"使用 ffmpeg 提取音频成功: {audio_path}")
                return audio_path
        except subprocess.CalledProcessError as e:
            logger.warning(f"ffmpeg 提取音频失败: {e}")
        except FileNotFoundError:
            logger.warning("ffmpeg 未安装，尝试使用 pydub")
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg 提取音频超时")

        # 方法2: 使用 pydub（纯 Python，无需 ffmpeg）
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(str(video_path))
            # 转换为 Whisper 推荐的格式：16kHz 单声道
            audio = audio.set_frame_rate(16000).set_channels(1)
            audio.export(str(audio_path), format="wav")
            if audio_path.exists() and audio_path.stat().st_size > 0:
                logger.info(f"使用 pydub 提取音频成功: {audio_path}")
                return audio_path
        except ImportError:
            logger.warning("pydub 未安装")
        except Exception as e:
            logger.warning(f"pydub 提取音频失败: {e}")

        # 如果都失败了，抛出异常
        logger.error(f"无法从视频提取音频: {video_path}")
        raise RuntimeError(f"无法从视频提取音频: {video_path}")

    def _make_progress_hook(
        self,
        callback: Optional[ProgressCallback],
        start_percent: float,
        end_percent: float,
        multi_file: bool = False
    ):
        """创建进度回调钩子
        
        Args:
            callback: 进度回调函数
            start_percent: 起始百分比
            end_percent: 结束百分比
            multi_file: 是否为多文件下载（音视频分离），如果是则合并显示进度
        """
        # 用于多文件下载的状态跟踪
        if not hasattr(self, '_download_state'):
            self._download_state = {
                'total_bytes': 0,
                'downloaded_bytes': 0,
                'file_count': 0,
                'completed_files': 0
            }
        
        def hook(d):
            if callback is None:
                return

            if multi_file:
                # 多文件下载模式：合并显示进度
                if d["status"] == "downloading":
                    # 更新当前文件进度
                    current_downloaded = d.get("downloaded_bytes", 0)
                    current_total = d.get("total_bytes") or d.get("total_bytes_estimate", 1)

                    # 估算总进度（假设视频和音频大小相近）
                    # 视频占 70%，音频占 30%
                    if self._download_state['file_count'] == 0:
                        # 第一个文件（视频）
                        ratio = current_downloaded / current_total
                        percent = start_percent + ratio * (end_percent - start_percent) * 0.7
                    else:
                        # 第二个文件（音频）
                        ratio = current_downloaded / current_total
                        percent = start_percent + 0.7 * (end_percent - start_percent) + ratio * (end_percent - start_percent) * 0.3

                    callback(f"下载中... {ratio*100:.0f}%", percent)

                elif d["status"] == "finished":
                    self._download_state['completed_files'] += 1
                    if self._download_state['completed_files'] >= 2:
                        # 所有文件下载完成
                        self._download_state = {'total_bytes': 0, 'downloaded_bytes': 0, 'file_count': 0, 'completed_files': 0}
                        callback("下载完成", end_percent)
                    else:
                        callback("下载音频...", start_percent + 0.7 * (end_percent - start_percent))
                        self._download_state['file_count'] += 1
            else:
                # 单文件下载模式：原始逻辑
                if d["status"] == "downloading":
                    downloaded = d.get("downloaded_bytes", 0)
                    total = d.get("total_bytes") or d.get("total_bytes_estimate", 1)
                    if total > 0:
                        ratio = downloaded / total
                        percent = start_percent + ratio * (end_percent - start_percent)
                        callback(f"下载中... {ratio*100:.0f}%", percent)
                elif d["status"] == "finished":
                    callback("下载完成", end_percent)

        return hook

    def _find_file(self, title: str, extensions: List[str]) -> Path:
        """查找文件（支持子目录递归查找）"""
        # 在输出目录及其子目录中查找
        for ext in extensions:
            # 递归查找所有匹配的文件
            files = list(self.output_dir.rglob(f"*{ext}"))
            if files:
                # 优先返回精确匹配标题的文件
                for f in files:
                    if title in f.name:
                        logger.debug(f"找到文件: {f}")
                        return f
                # 否则返回最新的文件
                newest_file = max(files, key=lambda p: p.stat().st_mtime)
                logger.debug(f"找到最新文件: {newest_file}")
                return newest_file

        logger.error(f"未找到文件: {title} ({extensions})")
        raise FileNotFoundError(f"未找到文件: {title} ({extensions})")

    def _find_file_in_dir(self, directory: Path, extensions: List[str]) -> Path:
        """在指定目录中查找文件"""
        for ext in extensions:
            files = list(directory.glob(f"*{ext}"))
            if files:
                # 返回最新的文件
                newest_file = max(files, key=lambda p: p.stat().st_mtime)
                logger.debug(f"在目录中找到文件: {newest_file}")
                return newest_file

        logger.error(f"在目录 {directory} 中未找到文件: {extensions}")
        raise FileNotFoundError(f"在目录 {directory} 中未找到文件: {extensions}")

    def _detect_platform(self, url: str) -> str:
        """检测视频平台"""
        domain = urlparse(url).netloc.lower()

        if "bilibili" in domain:
            return "bilibili"
        elif "youtube" in domain or "youtu.be" in domain:
            return "youtube"
        elif "xiaohongshu" in domain:
            return "xiaohongshu"
        else:
            return "unknown"


# 测试代码
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    def print_progress(status: str, percent: float):
        print(f"[{percent:5.1f}%] {status}")

    # 测试仅下载音频
    print("=== 测试仅下载音频 ===")
    service = DownloadService(Path("./test_output"))
    result = service.download(
        "https://www.bilibili.com/video/BV19NpFzbETP/",
        download_video=False,
        progress_callback=print_progress
    )
    print(f"\n音频: {result.audio_path}")
    print(f"视频: {result.video_path}")

    # 测试下载视频+音频
    print("\n=== 测试下载视频+音频 ===")
    result2 = service.download(
        "https://www.bilibili.com/video/BV19NpFzbETP/",
        download_video=True,
        video_quality="720p",
        progress_callback=print_progress
    )
    print(f"\n音频: {result2.audio_path}")
    print(f"视频: {result2.video_path}")
