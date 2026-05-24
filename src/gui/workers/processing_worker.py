"""后台处理工作线程 - 执行视频处理任务"""

import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from uuid import uuid4

from PySide6.QtCore import QThread, Signal, QObject

# 导入服务
from ...models.task import VideoMetadata, ExportContext, ExportTarget, ProcessingMode, TranscriptSegment
from ...services.download_service import DownloadService, DownloadResult
from ...services.transcribe_service import TranscribeService
from ...services.ai_service import AIService, SummaryResult
from ...services.export_orchestrator import ExportOrchestrator
from ...exporters.html_player_exporter import HTMLPlayerExporter
from ...utils import get_logger
from ...config.constants import Defaults, ProgressWeights
from ...utils.platform_utils import URLValidator
from ...utils.retry import (
    RetryableOperation, RetryConfig, RetryStrategy,
    DOWNLOAD_RETRY_CONFIG, TRANSCRIBE_RETRY_CONFIG, AI_RETRY_CONFIG,
    is_retryable_error
)
from ...utils.exceptions import RetryableError
from ...services.time_estimator import get_time_estimator

logger = get_logger(__name__)


@dataclass
class TaskConfig:
    """任务配置"""
    task_id: str
    url: str
    mode: ProcessingMode
    targets: List[ExportTarget]
    output_dir: Path
    whisper_model: str = Defaults.WHISPER_MODEL
    ai_engine: str = Defaults.AI_ENGINE
    ai_model: str = Defaults.AI_MODEL
    api_key: Optional[str] = None
    download_video: bool = Defaults.DOWNLOAD_VIDEO
    video_quality: str = Defaults.VIDEO_QUALITY
    prompt_template_id: Optional[str] = None  # Prompt 模板 ID
    # Obsidian 配置
    obsidian_vault_path: Optional[Path] = None
    obsidian_subfolder: str = "Inbox/Videos"

    def __post_init__(self):
        """验证配置"""
        if not URLValidator.is_valid_url(self.url):
            raise ValueError(f"无效的 URL: {self.url}")


class ProcessingWorker(QThread):
    """
    后台处理工作线程

    信号:
        progress_updated: 进度更新 (task_id, progress_percent, message)
        status_changed: 状态变更 (task_id, status, message)
        task_completed: 任务完成 (task_id, success, result_info)
        task_failed: 任务失败 (task_id, error_message)
        title_updated: 标题更新 (task_id, title)
        task_paused: 任务已暂停 (task_id)
        task_resumed: 任务已恢复 (task_id)
        retrying: 正在重试 (task_id, attempt, max_attempts, error_message)
    """

    progress_updated = Signal(str, int, str)  # task_id, progress, message
    status_changed = Signal(str, str, str)    # task_id, status, message
    task_completed = Signal(str, bool, dict)  # task_id, success, result
    task_failed = Signal(str, str)            # task_id, error_message
    title_updated = Signal(str, str)          # task_id, title
    metadata_updated = Signal(str, int, str)  # task_id, duration_seconds, platform
    task_paused = Signal(str)                 # task_id
    task_resumed = Signal(str)                # task_id
    retrying = Signal(str, int, int, str)     # task_id, attempt, max_attempts, error

    def __init__(self, config: TaskConfig, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.config = config
        self._is_cancelled = False
        self._should_stop = False  # 安全停止标志
        self._is_paused = False    # 暂停标志
        self._pause_event = None   # 暂停事件（用于线程同步）

        # 初始化服务
        self.download_service = DownloadService(config.output_dir)
        self.transcribe_service = TranscribeService(model_size=config.whisper_model)
        self.ai_service: Optional[AIService] = None

        if config.api_key:
            try:
                self.ai_service = AIService(api_key=config.api_key)
            except Exception:
                self.ai_service = AIService(mock=True)
        else:
            self.ai_service = AIService(mock=True)

    def cancel(self):
        """取消任务"""
        self._is_cancelled = True
        self._should_stop = True
        self.requestInterruption()
        # 如果处于暂停状态，恢复执行以便退出
        self._is_paused = False

    def pause(self):
        """暂停任务"""
        if not self._is_paused:
            self._is_paused = True
            logger.info(f"Task {self.config.task_id} paused")
            self.task_paused.emit(self.config.task_id)

    def resume(self):
        """恢复任务"""
        if self._is_paused:
            self._is_paused = False
            logger.info(f"Task {self.config.task_id} resumed")
            self.task_resumed.emit(self.config.task_id)

    def _check_paused(self):
        """检查是否处于暂停状态，如果是则等待"""
        while self._is_paused and not self._should_stop and not self.isInterruptionRequested():
            # 使用短间隔轮询，避免阻塞线程
            self.msleep(100)  # 100ms

    def run(self):
        """执行处理流程"""
        task_id = self.config.task_id
        mode = self.config.mode
        logger.debug(f"ProcessingWorker.run() started for task {task_id}")

        # 记录任务开始时间
        time_estimator = get_time_estimator()
        time_estimator.record_task_start(task_id)

        # 视频时长（将在下载后更新）
        video_duration = 0
        platform = ""

        try:
            # 根据模式执行不同流程
            if mode == ProcessingMode.DOWNLOAD_ONLY:
                video_duration, platform = self._process_download_only(task_id)
            elif mode == ProcessingMode.TRANSCRIBE_ONLY:
                video_duration, platform = self._process_transcribe_only(task_id)
            elif mode == ProcessingMode.FULL:
                video_duration, platform = self._process_full(task_id)
            else:
                raise ValueError(f"Unknown processing mode: {mode}")

            # 记录任务完成统计
            if video_duration > 0:
                time_estimator.record_task_complete(
                    task_id=task_id,
                    mode=mode.value,
                    platform=platform,
                    video_duration=video_duration
                )

        except InterruptedError:
            logger.info(f"Task {task_id} was cancelled")
            self.task_failed.emit(task_id, "任务已取消")
        except Exception as e:
            logger.exception(f"Exception in worker for task {task_id}")
            self.task_failed.emit(task_id, str(e))
        finally:
            # 确保释放资源
            self._cleanup_resources()

    def _cleanup_resources(self):
        """清理资源"""
        try:
            # 关闭 AI Service 的 HTTP 客户端
            if self.ai_service:
                self.ai_service.close()
                logger.debug("AI Service HTTP client closed")
        except Exception as e:
            logger.warning(f"Error cleaning up resources: {e}")

    def _check_cancelled(self) -> bool:
        """检查是否已取消或中断（同时检查暂停状态）"""
        # 先检查暂停状态
        self._check_paused()
        return self._is_cancelled or self.isInterruptionRequested() or self._should_stop

    def _check_should_stop(self, task_id: str, operation_name: str = "操作") -> None:
        """
        检查是否应该停止，如果是则抛出 InterruptedError

        Args:
            task_id: 任务ID
            operation_name: 操作名称（用于错误信息）

        Raises:
            InterruptedError: 如果任务应该停止
        """
        if self._should_stop:
            logger.debug(f"任务 {task_id} 在{operation_name}后检测到停止请求")
            raise InterruptedError("任务已取消")

    def _create_progress_callback(
        self,
        task_id: str,
        base_progress: int,
        weight: float
    ) -> callable:
        """
        创建进度回调函数

        Args:
            task_id: 任务ID
            base_progress: 基础进度值
            weight: 权重（0-1之间）

        Returns:
            callable: 进度回调函数
        """
        def callback(status: str, percent: float) -> None:
            if self._check_cancelled():
                self._should_stop = True
                return
            progress = base_progress + int(percent * weight)
            self.progress_updated.emit(task_id, progress, status)

        return callback

    def _process_download_only(self, task_id: str) -> tuple[int, str]:
        """仅下载模式"""
        self.status_changed.emit(task_id, "downloading", "开始下载...")

        # 下载
        result = self.download_service.download(
            self.config.url,
            download_video=self.config.download_video,
            video_quality=self.config.video_quality,
            progress_callback=self._create_progress_callback(task_id, 0, 1.0)
        )

        # 下载完成后检查是否需要停止
        self._check_should_stop(task_id, "下载")

        # 更新标题和元数据
        self.title_updated.emit(task_id, result.metadata.title)
        self.metadata_updated.emit(task_id, result.metadata.duration, result.metadata.platform)
        self.status_changed.emit(task_id, "completed", "下载完成")
        self.progress_updated.emit(task_id, 100, "完成")

        # 仅下载模式没有使用 ExportOrchestrator，所以导出成功数为 0
        # 下载的文件保存在本地，算作一种"导出"
        export_success = 1  # 下载成功即算导出成功
        export_total = 1

        self.task_completed.emit(task_id, True, {
            "video_path": str(result.video_path) if result.video_path else None,
            "audio_path": str(result.audio_path),
            "title": result.metadata.title,
            "highlights_count": 0,  # 仅下载模式没有提取要点
            "export_success": export_success,
            "export_total": export_total,
            "export_results": []
        })

        return result.metadata.duration, result.metadata.platform

    def _process_transcribe_only(self, task_id: str) -> tuple[int, str]:
        """转录存档模式"""
        # 步骤1: 下载 (30%)
        self.status_changed.emit(task_id, "downloading", "下载音频...")

        download_result = self.download_service.download(
            self.config.url,
            download_video=False,
            progress_callback=self._create_progress_callback(task_id, 0, ProgressWeights.DOWNLOAD)
        )

        self._check_should_stop(task_id, "下载")

        self.title_updated.emit(task_id, download_result.metadata.title)
        self.metadata_updated.emit(task_id, download_result.metadata.duration, download_result.metadata.platform)

        # 步骤2: 转录 (50%)
        self.status_changed.emit(task_id, "transcribing", "语音转录中...")

        transcript_result = self.transcribe_service.transcribe(
            download_result.audio_path,
            language="zh",
            progress_callback=self._create_progress_callback(
                task_id,
                int(ProgressWeights.DOWNLOAD * 100),
                ProgressWeights.TRANSCRIBE
            )
        )

        self._check_should_stop(task_id, "转录")

        # 保存 SRT 到下载目录
        srt_path = download_result.audio_path.with_suffix(".srt")
        srt_content = self._generate_srt(transcript_result.segments)
        srt_path.write_text(srt_content, encoding="utf-8")

        # 步骤3: 导出到本地文件夹 (20%)
        # 转录模式只导出到本地文件夹，不导出到 Obsidian（保持轻量级）
        self.status_changed.emit(task_id, "exporting", "导出到本地文件夹...")
        self.progress_updated.emit(task_id, 80, "导出中...")

        # 构建导出上下文（转录模式没有 AI 摘要）
        export_context = ExportContext(
            task_id=uuid4(),
            video_metadata=download_result.metadata,
            video_path=None,  # 转录模式不下载视频
            audio_path=download_result.audio_path,
            transcript_segments=transcript_result.segments,
            transcript_text=transcript_result.formatted_text,
            ai_summary=None,  # 转录模式没有 AI 摘要
            config={}  # 转录模式没有时间轴 highlights
        )

        # 构建导出配置（只导出到本地）
        export_config = {
            "local_output_path": self.config.output_dir,
            "organize_by": "date",
        }

        # 只导出到本地文件夹
        orchestrator = ExportOrchestrator(targets=[ExportTarget.LOCAL], config=export_config)
        export_results = orchestrator.export_all(export_context)

        self.status_changed.emit(task_id, "completed", "转录完成")
        self.progress_updated.emit(task_id, 100, "完成")

        # 构建导出结果信息
        export_success = sum(1 for r in export_results if r and getattr(r, 'success', False))
        export_total = len(export_results)

        self.task_completed.emit(task_id, True, {
            "audio_path": str(download_result.audio_path),
            "srt_path": str(srt_path),
            "title": download_result.metadata.title,
            "segments_count": len(transcript_result.segments),
            "highlights_count": 0,  # 转录模式没有提取要点
            "export_success": export_success,
            "export_total": export_total,
            "export_results": export_results
        })

        return download_result.metadata.duration, download_result.metadata.platform

    def _process_full(self, task_id: str) -> tuple[int, str]:
        """完整处理模式"""
        # 步骤1: 下载 (20%)
        self.status_changed.emit(task_id, "downloading", "下载视频...")

        download_result = self.download_service.download(
            self.config.url,
            download_video=self.config.download_video,
            video_quality=self.config.video_quality,
            progress_callback=self._create_progress_callback(task_id, 0, 0.2)
        )

        self._check_should_stop(task_id, "下载")
        self.title_updated.emit(task_id, download_result.metadata.title)
        self.metadata_updated.emit(task_id, download_result.metadata.duration, download_result.metadata.platform)

        # 步骤2: 转录 (40%)
        self.status_changed.emit(task_id, "transcribing", "语音转录中...")

        transcript_result = self.transcribe_service.transcribe(
            download_result.audio_path,
            language="zh",
            progress_callback=self._create_progress_callback(task_id, 20, 0.4)
        )

        self._check_should_stop(task_id, "转录")

        # 步骤3: AI 摘要 (25%) - 带重试和模型切换
        self.status_changed.emit(task_id, "ai_processing", "AI 生成摘要...")
        self.progress_updated.emit(task_id, 60, "AI 处理中...")

        if self._check_cancelled():
            raise InterruptedError("任务已取消")

        # 使用重试机制调用 AI 服务
        summary_result = self._summarize_with_retry(
            task_id=task_id,
            transcript=transcript_result.full_text,
            title=download_result.metadata.title,
            template_id=self.config.prompt_template_id
        )

        self.progress_updated.emit(task_id, 85, "摘要生成完成")

        # 步骤4: 导出 (15%)
        self.status_changed.emit(task_id, "exporting", "导出到目标...")
        self.progress_updated.emit(task_id, 85, "导出中...")

        # 构建导出上下文
        export_context = ExportContext(
            task_id=uuid4(),
            video_metadata=download_result.metadata,
            video_path=download_result.video_path,
            audio_path=download_result.audio_path,
            transcript_segments=transcript_result.segments,
            transcript_text=transcript_result.formatted_text,
            ai_summary=summary_result.summary if summary_result else None,
            config={
                "highlights": [
                    {"time": h.time, "seconds": h.seconds, "content": h.content}
                    for h in summary_result.highlights
                ] if summary_result else []
            }
        )

        # 解析用户选择的目标
        targets = self._parse_targets(self.config.targets)

        # 构建导出配置
        export_config = {
            "local_output_path": self.config.output_dir,
            "organize_by": "date",
        }

        # 设置 Obsidian 配置（从 TaskConfig 获取）
        if self.config.obsidian_vault_path:
            export_config["obsidian_vault_path"] = self.config.obsidian_vault_path
        export_config["obsidian_subfolder"] = self.config.obsidian_subfolder

        # 策略：始终先导出到本地文件夹（作为基础存储）
        # 然后如果选择了其他目标，再导出到那些目标
        all_targets = [ExportTarget.LOCAL]  # 始终包含本地
        if ExportTarget.LOCAL not in targets:
            # 用户没有选择本地，但我们需要它作为基础
            pass  # 本地始终包含
        # 添加用户选择的其他目标
        for t in targets:
            if t not in all_targets:
                all_targets.append(t)

        orchestrator = ExportOrchestrator(targets=all_targets, config=export_config)
        export_results = orchestrator.export_all(export_context)

        # 生成 HTML 播放器（始终生成，因为视频在本地）
        if download_result.video_path and summary_result and summary_result.highlights:
            try:
                html_exporter = HTMLPlayerExporter()
                html_result = html_exporter.export(export_context)
                if html_result.success:
                    logger.debug(f"任务 {task_id} HTML 播放器生成成功")
            except Exception as e:
                # HTML 播放器生成失败不影响主流程，但记录日志
                logger.warning(f"任务 {task_id} HTML 播放器生成失败: {e}")

        self.progress_updated.emit(task_id, 100, "完成")
        self.status_changed.emit(task_id, "completed", "处理完成")

        # 统计导出结果
        success_count = sum(1 for r in export_results if r.success)

        self.task_completed.emit(task_id, True, {
            "title": download_result.metadata.title,
            "video_path": str(download_result.video_path) if download_result.video_path else None,
            "audio_path": str(download_result.audio_path),
            "segments_count": len(transcript_result.segments),
            "highlights_count": len(summary_result.highlights) if summary_result else 0,
            "export_success": success_count,
            "export_total": len(export_results),
            "export_results": export_results  # 添加导出结果列表
        })

        return download_result.metadata.duration, download_result.metadata.platform

    def _parse_targets(self, targets_config: List[Any]) -> List[ExportTarget]:
        """解析目标配置"""
        target_map = {
            "obsidian": ExportTarget.OBSIDIAN,
            "local": ExportTarget.LOCAL,
            "notion": ExportTarget.NOTION,
        }

        targets = []
        for t in targets_config:
            # 处理 ExportTarget 枚举对象
            if isinstance(t, ExportTarget):
                targets.append(t)
            # 处理字典类型（从GUI传入）
            elif isinstance(t, dict):
                target_type = t.get("type", "")
                if isinstance(target_type, ExportTarget):
                    targets.append(target_type)
                elif isinstance(target_type, str) and target_type.lower() in target_map:
                    targets.append(target_map[target_type.lower()])
            # 处理字符串类型
            elif isinstance(t, str) and t.lower() in target_map:
                targets.append(target_map[t.lower()])

        return targets if targets else [ExportTarget.LOCAL]

    def _summarize_with_retry(
        self,
        task_id: str,
        transcript: str,
        title: str,
        template_id: str
    ) -> Optional[Any]:
        """
        带重试机制的 AI 摘要生成

        支持：
        - 指数退避重试
        - 失败时自动切换模型
        - 重试状态报告

        Returns:
            Optional[Any]: AI 摘要结果，失败时抛出异常
        """
        from ...utils.exceptions import AIError, NetworkError, TimeoutError, ServiceUnavailableError

        max_retries = 3
        base_delay = 1.0
        last_error = None

        # 可用的备用模型（按优先级排序）- 使用项目支持的国内模型
        fallback_models = ["deepseek-chat", "glm-4", "moonshot-v1-8k"]
        current_model = self.ai_service.model if self.ai_service else fallback_models[0]

        for attempt in range(1, max_retries + 1):
            try:
                # 尝试生成摘要
                result = self.ai_service.summarize(
                    transcript=transcript,
                    title=title,
                    template_id=template_id
                )

                if result:
                    logger.info(f"任务 {task_id} AI 摘要在第 {attempt} 次尝试成功")
                    return result

                # 如果返回 None，可能是模型问题，尝试切换
                raise AIError("AI 返回空结果", error_code="EMPTY_RESPONSE")

            except (AIError, NetworkError, TimeoutError, ServiceUnavailableError) as e:
                last_error = e

                # 检查是否可重试
                if not is_retryable_error(e):
                    logger.warning(f"任务 {task_id} AI 错误不可重试: {e}")
                    raise

                if attempt >= max_retries:
                    logger.error(f"任务 {task_id} AI 摘要在 {max_retries} 次尝试后失败: {e}")
                    raise

                # 计算延迟（指数退避）
                delay = base_delay * (2 ** (attempt - 1))
                delay = min(delay, 30.0)  # 最大延迟 30 秒

                # 添加抖动
                import random
                delay += random.uniform(0, 1)

                # 发送重试信号
                error_msg = str(e)[:100]  # 限制错误消息长度
                self.retrying.emit(task_id, attempt, max_retries, error_msg)
                self.status_changed.emit(
                    task_id,
                    "ai_retrying",
                    f"AI 处理失败，{delay:.1f}秒后重试（{attempt}/{max_retries}）..."
                )

                logger.warning(
                    f"任务 {task_id} AI 摘要第 {attempt} 次尝试失败: {e}，"
                    f"{delay:.1f}秒后重试..."
                )

                # 等待延迟
                time.sleep(delay)

                # 尝试切换模型（如果可能）
                if attempt == 2 and not self.ai_service.mock:
                    # 第二次失败后尝试切换模型
                    current_idx = fallback_models.index(current_model) if current_model in fallback_models else -1
                    if current_idx >= 0 and current_idx < len(fallback_models) - 1:
                        new_model = fallback_models[current_idx + 1]
                        logger.info(f"任务 {task_id} 尝试切换到备用模型: {new_model}")
                        try:
                            # 根据模型选择对应的 API 端点
                            from ...services.ai_service import AIService
                            base_url = AIService.DEFAULT_ENDPOINTS.get(
                                self._get_engine_for_model(new_model),
                                self.ai_service.base_url
                            )

                            # 创建新的 AI 服务实例（使用相同 API Key 但不同模型）
                            self.ai_service = AIService(
                                api_key=self.ai_service.api_key,
                                base_url=base_url,
                                model=new_model
                            )
                            current_model = new_model
                            self.status_changed.emit(
                                task_id,
                                "ai_retrying",
                                f"已切换到备用模型: {new_model}"
                            )
                        except Exception as switch_error:
                            logger.warning(f"切换模型失败: {switch_error}")

        # 所有重试都失败了
        raise last_error if last_error else AIError("AI 摘要生成失败")

    @staticmethod
    def _generate_srt(segments: List[TranscriptSegment]) -> str:
        """生成 SRT 字幕（使用共享工具）"""
        from ...utils import generate_srt
        return generate_srt(segments)

    @staticmethod
    def _get_engine_for_model(model: str) -> str:
        """根据模型名称获取对应的引擎标识"""
        model_engine_map = {
            "deepseek-chat": "deepseek",
            "deepseek-reasoner": "deepseek",
            "glm-4": "zhipu",
            "glm-4v": "zhipu",
            "moonshot-v1-8k": "moonshot",
            "moonshot-v1-32k": "moonshot",
            "moonshot-v1-128k": "moonshot",
        }
        return model_engine_map.get(model, "deepseek")
