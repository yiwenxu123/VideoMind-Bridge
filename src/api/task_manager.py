"""API任务管理器

管理API任务的生命周期，协调各个服务组件。
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set
from uuid import UUID, uuid4

from ..models.task import (
    VideoTask,
    TaskStatus,
    ProcessingMode,
    ExportTarget,
    VideoMetadata,
)
from ..services.task_database import TaskDatabase, get_task_database
from ..services.download_service import DownloadService
from ..services.transcribe_service import TranscribeService
from ..services.ai_service import AIService
from ..services.export_orchestrator import ExportOrchestrator
from ..utils import get_logger

logger = get_logger(__name__)


class TaskManager:
    """API任务管理器"""

    def __init__(self, output_dir: Optional[Path] = None):
        """
        初始化任务管理器

        Args:
            output_dir: 输出目录，默认为项目目录下的 output
        """
        if output_dir is None:
            # 使用项目目录下的 output 文件夹
            project_root = Path(__file__).parent.parent.parent
            output_dir = project_root / "output"
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 数据库
        self.db = get_task_database()

        # 活跃任务
        self._tasks: Dict[UUID, VideoTask] = {}
        self._task_callbacks: Dict[UUID, List[Callable]] = {}

        # 服务组件
        self._download_service = DownloadService(self.output_dir)
        self._transcribe_service = TranscribeService()
        # AI服务使用mock模式，避免需要配置API Key
        self._ai_service = AIService(mock=True)
        # 导出编排器，默认导出到本地
        self._export_orchestrator = ExportOrchestrator(
            targets=[ExportTarget.LOCAL],
            config={"local_output_path": self.output_dir}
        )

        # 运行状态
        self._running = False
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """启动任务管理器"""
        if self._running:
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._process_queue())
        logger.info("任务管理器已启动")

    async def stop(self) -> None:
        """停止任务管理器"""
        self._running = False

        # 取消所有活跃任务
        for task_id in list(self._tasks.keys()):
            await self.cancel_task(task_id)

        # 停止工作线程
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        logger.info("任务管理器已停止")

    async def create_task(
        self,
        url: str,
        mode: ProcessingMode = ProcessingMode.FULL,
        targets: Optional[Set[ExportTarget]] = None,
        ai_provider: Optional[str] = None,
        ai_prompt: Optional[str] = None,
    ) -> VideoTask:
        """
        创建新任务

        Args:
            url: 视频链接
            mode: 处理模式
            targets: 导出目标
            ai_provider: AI提供商
            ai_prompt: AI提示词

        Returns:
            创建的任务对象
        """
        task = VideoTask(
            id=uuid4(),
            url=url,
            mode=mode,
            targets=targets or {ExportTarget.LOCAL},
            ai_provider=ai_provider,
            ai_prompt=ai_prompt,
            status=TaskStatus.PENDING,
            progress=0.0,
            current_step="等待中",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # 解析视频元数据
        try:
            metadata = await self._download_service.extract_metadata(url)
            task.metadata = metadata
            task.current_step = "已解析视频信息"
        except Exception as e:
            logger.warning(f"解析视频元数据失败: {e}")
            task.metadata = VideoMetadata(
                title="未知标题",
                author="未知作者",
                duration=0,
                platform="unknown",
                url=url,
            )

        # 保存任务
        self._tasks[task.id] = task
        await self._task_queue.put(task.id)

        logger.info(f"任务已创建: {task.id}")
        return task

    async def get_task(self, task_id: UUID) -> Optional[VideoTask]:
        """
        获取任务

        Args:
            task_id: 任务ID

        Returns:
            任务对象，如果不存在则返回None
        """
        return self._tasks.get(task_id)

    async def get_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[VideoTask]:
        """
        获取任务列表

        Args:
            status: 按状态筛选
            limit: 数量限制
            offset: 偏移量

        Returns:
            任务列表
        """
        tasks = list(self._tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]

        # 按创建时间排序
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        return tasks[offset:offset + limit]

    async def cancel_task(self, task_id: UUID) -> bool:
        """
        取消任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功取消
        """
        task = self._tasks.get(task_id)
        if not task:
            return False

        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return False

        task.status = TaskStatus.CANCELLED
        task.updated_at = datetime.now()
        task.current_step = "已取消"

        self._notify_task_update(task)
        logger.info(f"任务已取消: {task_id}")
        return True

    async def delete_task(self, task_id: UUID) -> bool:
        """
        删除任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功删除
        """
        task = self._tasks.get(task_id)
        if not task:
            return False

        # 如果任务正在运行，先取消
        if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            await self.cancel_task(task_id)

        del self._tasks[task_id]
        if task_id in self._task_callbacks:
            del self._task_callbacks[task_id]

        logger.info(f"任务已删除: {task_id}")
        return True

    def register_callback(
        self,
        task_id: UUID,
        callback: Callable[[VideoTask], None],
    ) -> None:
        """
        注册任务更新回调

        Args:
            task_id: 任务ID
            callback: 回调函数
        """
        if task_id not in self._task_callbacks:
            self._task_callbacks[task_id] = []
        self._task_callbacks[task_id].append(callback)

    def unregister_callback(
        self,
        task_id: UUID,
        callback: Callable[[VideoTask], None],
    ) -> None:
        """
        注销任务更新回调

        Args:
            task_id: 任务ID
            callback: 回调函数
        """
        if task_id in self._task_callbacks:
            self._task_callbacks[task_id] = [
                cb for cb in self._task_callbacks[task_id] if cb != callback
            ]

    def _notify_task_update(self, task: VideoTask) -> None:
        """通知任务更新"""
        callbacks = self._task_callbacks.get(task.id, [])
        for callback in callbacks:
            try:
                callback(task)
            except Exception as e:
                logger.error(f"任务更新回调失败: {e}")

    async def _process_queue(self) -> None:
        """处理任务队列"""
        while self._running:
            try:
                task_id = await asyncio.wait_for(
                    self._task_queue.get(),
                    timeout=1.0,
                )
                await self._execute_task(task_id)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理任务队列时出错: {e}")

    async def _execute_task(self, task_id: UUID) -> None:
        """
        执行任务

        Args:
            task_id: 任务ID
        """
        task = self._tasks.get(task_id)
        if not task:
            return

        if task.status == TaskStatus.CANCELLED:
            return

        task.status = TaskStatus.DOWNLOADING
        task.current_step = "正在下载视频..."
        task.progress = 10.0
        task.updated_at = datetime.now()
        self._notify_task_update(task)

        try:
            # 1. 下载
            audio_path = await self._download_audio(task)
            if not audio_path:
                raise Exception("下载失败")

            task.audio_path = audio_path
            task.progress = 30.0
            self._notify_task_update(task)

            # 2. 转录
            if task.status != TaskStatus.CANCELLED:
                task.status = TaskStatus.TRANSCRIBING
                task.current_step = "正在转录音频..."
                task.progress = 40.0
                self._notify_task_update(task)

                segments = await self._transcribe_audio(task, audio_path)
                task.transcript_segments = segments
                task.progress = 60.0
                self._notify_task_update(task)

            # 3. AI处理
            if task.status != TaskStatus.CANCELLED and task.mode == ProcessingMode.FULL:
                task.status = TaskStatus.AI_PROCESSING
                task.current_step = "正在生成AI摘要..."
                task.progress = 70.0
                self._notify_task_update(task)

                summary = await self._generate_summary(task)
                task.ai_summary = summary
                task.progress = 85.0
                self._notify_task_update(task)

            # 4. 导出
            if task.status != TaskStatus.CANCELLED:
                task.status = TaskStatus.EXPORTING
                task.current_step = "正在导出..."
                task.progress = 90.0
                self._notify_task_update(task)

                await self._export_results(task)

            # 完成
            if task.status != TaskStatus.CANCELLED:
                task.status = TaskStatus.COMPLETED
                task.current_step = "已完成"
                task.progress = 100.0
                task.updated_at = datetime.now()
                logger.info(f"任务完成: {task_id}")

        except Exception as e:
            logger.error(f"任务执行失败: {task_id}, 错误: {e}")
            task.status = TaskStatus.FAILED
            task.error_msg = str(e)
            task.current_step = f"失败: {e}"
            task.updated_at = datetime.now()

        self._notify_task_update(task)

    async def _download_audio(self, task: VideoTask) -> Optional[Path]:
        """下载音频"""
        try:
            output_path = self.output_dir / f"{task.id}.m4a"
            await self._download_service.download_audio(
                task.url,
                output_path,
                progress_callback=lambda p: self._update_download_progress(task, p),
            )
            return output_path
        except Exception as e:
            logger.error(f"下载音频失败: {e}")
            return None

    def _update_download_progress(self, task: VideoTask, progress: float) -> None:
        """更新下载进度"""
        task.progress = 10.0 + progress * 0.2  # 10% - 30%
        self._notify_task_update(task)

    async def _transcribe_audio(
        self,
        task: VideoTask,
        audio_path: Path,
    ) -> List:
        """转录音频"""
        try:
            segments = await self._transcribe_service.transcribe(
                audio_path,
                progress_callback=lambda p: self._update_transcribe_progress(task, p),
            )
            return segments
        except Exception as e:
            logger.error(f"转录音频失败: {e}")
            raise

    def _update_transcribe_progress(self, task: VideoTask, progress: float) -> None:
        """更新转录进度"""
        task.progress = 40.0 + progress * 0.2  # 40% - 60%
        self._notify_task_update(task)

    async def _generate_summary(self, task: VideoTask) -> str:
        """生成AI摘要"""
        try:
            transcript_text = "\n".join([
                f"[{s.start:.1f}s] {s.text}" for s in task.transcript_segments
            ])

            summary = await self._ai_service.generate_summary(
                transcript_text,
                provider=task.ai_provider,
                prompt_template=task.ai_prompt,
                progress_callback=lambda p: self._update_ai_progress(task, p),
            )
            return summary
        except Exception as e:
            logger.error(f"生成摘要失败: {e}")
            raise

    def _update_ai_progress(self, task: VideoTask, progress: float) -> None:
        """更新AI处理进度"""
        task.progress = 70.0 + progress * 0.15  # 70% - 85%
        self._notify_task_update(task)

    async def _export_results(self, task: VideoTask) -> None:
        """导出结果"""
        try:
            # TODO: 实现导出逻辑
            pass
        except Exception as e:
            logger.error(f"导出失败: {e}")
            raise

    def get_statistics(self) -> Dict:
        """获取统计信息"""
        stats = {
            "total": len(self._tasks),
            "active": 0,
            "queued": 0,
            "completed": 0,
            "failed": 0,
        }

        for task in self._tasks.values():
            if task.status in (TaskStatus.DOWNLOADING, TaskStatus.TRANSCRIBING, TaskStatus.AI_PROCESSING, TaskStatus.EXPORTING):
                stats["active"] += 1
            elif task.status == TaskStatus.PENDING:
                stats["queued"] += 1
            elif task.status == TaskStatus.COMPLETED:
                stats["completed"] += 1
            elif task.status == TaskStatus.FAILED:
                stats["failed"] += 1

        return stats
