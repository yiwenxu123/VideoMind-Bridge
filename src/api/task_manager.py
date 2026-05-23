"""API任务管理器

管理API任务的生命周期，协调各个服务组件。
遵循依赖倒置原则：依赖抽象接口而非具体实现。
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, TYPE_CHECKING
from uuid import UUID, uuid4

from ..models.task import (
    VideoTask,
    TaskStatus,
    ProcessingMode,
    ExportTarget,
    VideoMetadata,
    TaskHistory,
)
from ..services.task_database import TaskDatabase, get_task_database
from ..services.download_service import DownloadService
from ..services.transcribe_service import TranscribeService
from ..services.ai_service import AIService
from ..services.export_orchestrator import ExportOrchestrator
from ..services.config_manager import get_config_manager
from ..services.interfaces import (
    IDownloadService,
    ITranscribeService,
    IAIProvider,
    IExportOrchestrator,
)
from ..utils import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class TaskManager:
    """API任务管理器
    
    协调各服务组件完成视频处理流程：
    下载 → 转录 → AI摘要 → 导出
    
    服务组件通过接口类型声明，支持未来替换为 Skills 实现。
    """

    def __init__(self, output_dir: Optional[Path] = None):
        """
        初始化任务管理器

        Args:
            output_dir: 输出目录，默认为项目目录下的 output
        """
        if output_dir is None:
            project_root = Path(__file__).parent.parent.parent
            output_dir = project_root / "output"
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.db = get_task_database()

        self._tasks: Dict[UUID, VideoTask] = {}
        self._task_callbacks: Dict[UUID, List[Callable]] = {}

        self._download_service: IDownloadService = DownloadService(self.output_dir)
        self._transcribe_service: ITranscribeService = TranscribeService()
        
        self._config_manager = get_config_manager()
        api_key = self._config_manager.get_api_key()
        if api_key:
            self._ai_service: IAIProvider = AIService(
                api_key=api_key, 
                model=self._config_manager.ai.model
            )
            logger.info(f"AI服务已启用，模型: {self._config_manager.ai.model}")
        else:
            self._ai_service = AIService(mock=True)
            logger.warning("AI服务使用mock模式，未配置API Key")
        
        self._export_orchestrator: IExportOrchestrator = ExportOrchestrator(
            targets=[ExportTarget.LOCAL],
            config={"local_output_path": self.output_dir}
        )

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
        cookies_from_browser: Optional[str] = None,
    ) -> VideoTask:
        """
        创建新任务

        Args:
            url: 视频链接
            mode: 处理模式
            targets: 导出目标
            ai_provider: AI提供商
            ai_prompt: AI提示词
            cookies_from_browser: 浏览器名称（chrome/safari/firefox）

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
        task.cookies_from_browser = cookies_from_browser

        # 暂不解析元数据，下载时一并获取
        task.metadata = VideoMetadata(
            title="获取中...",
            author="未知",
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

        self._save_task_to_db(task)

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
            loop = asyncio.get_event_loop()
            
            def do_download():
                result = self._download_service.download(
                    task.url,
                    download_video=False,
                    progress_callback=lambda status, percent: self._update_download_progress(task, percent),
                    cookies_from_browser=getattr(task, 'cookies_from_browser', None),
                )
                return result

            result = await loop.run_in_executor(None, do_download)
            
            if result and result.audio_path:
                if result.metadata:
                    task.metadata = result.metadata
                return result.audio_path
            
            return None
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
            loop = asyncio.get_event_loop()
            
            def do_transcribe():
                return self._transcribe_service.transcribe(
                    audio_path,
                    language="zh",
                )
            
            result = await loop.run_in_executor(None, do_transcribe)
            
            if result and hasattr(result, 'segments'):
                return result.segments
            return []
        except Exception as e:
            logger.error(f"转录音频失败: {e}")
            raise

    async def _generate_summary(self, task: VideoTask) -> str:
        """生成AI摘要"""
        try:
            transcript_text = "\n".join([
                f"[{s.start:.1f}s] {s.text}" for s in task.transcript_segments
            ])

            loop = asyncio.get_event_loop()
            
            def do_summarize():
                result = self._ai_service.summarize(
                    transcript=transcript_text,
                    title=task.metadata.title if task.metadata else "",
                )
                return result
            
            result = await loop.run_in_executor(None, do_summarize)
            
            if result and hasattr(result, 'summary'):
                return result.summary
            return ""
        except Exception as e:
            logger.error(f"生成摘要失败: {e}")
            raise

    async def _export_results(self, task: VideoTask) -> None:
        """导出结果"""
        try:
            task.output_files = []
            
            if not task.audio_path or not task.audio_path.exists():
                logger.warning(f"音频文件不存在，跳过导出: {task.audio_path}")
                return
            
            from ..models.task import ExportContext, VideoMetadata
            
            metadata = task.metadata or VideoMetadata(
                title="未知标题",
                author="",
                duration=0,
                platform="unknown",
                url=task.url,
            )
            
            context = ExportContext(
                task_id=task.id,
                video_metadata=metadata,
                video_path=None,
                audio_path=task.audio_path,
                transcript_path=None,
                transcript_segments=task.transcript_segments,
                transcript_text="\n".join([s.text for s in task.transcript_segments]) if task.transcript_segments else "",
                ai_summary=task.ai_summary,
            )
            
            results = self._export_orchestrator.export_all(context)
            
            for result in results:
                if result.success and result.output_path:
                    task.output_files.append(result.output_path)
                    logger.info(f"导出成功: {result.output_path}")
                elif not result.success:
                    logger.warning(f"导出失败: {result.error_msg}")
            
            logger.info(f"导出完成，共 {len(task.output_files)} 个文件")
        except Exception as e:
            logger.error(f"导出失败: {e}")
            raise

    def _save_task_to_db(self, task: VideoTask) -> None:
        """保存任务到数据库"""
        try:
            task_history = TaskHistory(
                id=str(task.id),
                url=task.url,
                title=task.metadata.title if task.metadata else "未知标题",
                author=task.metadata.author if task.metadata else "",
                platform=task.metadata.platform if task.metadata else "unknown",
                mode=task.mode,
                targets=list(task.targets),
                status=task.status,
                error_msg=task.error_msg,
                created_at=task.created_at,
                completed_at=datetime.now() if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED) else None,
                summary=task.ai_summary,
                highlights_count=0,
                transcript_path=task.audio_path,
                output_files=task.output_files if hasattr(task, 'output_files') and task.output_files else [],
                export_success_count=0,
                export_total_count=len(task.targets),
            )
            self.db.save_task(task_history)
            logger.debug(f"任务已保存到数据库: {task.id}")
        except Exception as e:
            logger.error(f"保存任务到数据库失败: {e}")

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
