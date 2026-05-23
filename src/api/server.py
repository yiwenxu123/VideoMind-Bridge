"""API服务器

基于FastAPI的REST API和WebSocket服务。
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Set
from uuid import UUID

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status

from ..models.task import ProcessingMode, ExportTarget, TaskStatus, VideoTask
from ..utils import get_logger
from .models import (
    TaskCreateRequest,
    TaskResponse,
    TaskListResponse,
    ProgressUpdate,
    APIError,
    TaskSearchRequest,
    SystemStatusResponse,
    ConfigResponse,
)
from .task_manager import TaskManager

logger = get_logger(__name__)


class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.task_subscriptions: Dict[UUID, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket):
        """接受WebSocket连接"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket连接已建立: {websocket.client}")

    def disconnect(self, websocket: WebSocket):
        """断开WebSocket连接"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        # 从所有订阅中移除
        for task_id, connections in self.task_subscriptions.items():
            connections.discard(websocket)

        logger.info(f"WebSocket连接已断开: {websocket.client}")

    def subscribe_to_task(self, task_id: UUID, websocket: WebSocket):
        """订阅任务更新"""
        if task_id not in self.task_subscriptions:
            self.task_subscriptions[task_id] = set()
        self.task_subscriptions[task_id].add(websocket)
        logger.debug(f"WebSocket订阅任务: {task_id}")

    def unsubscribe_from_task(self, task_id: UUID, websocket: WebSocket):
        """取消订阅任务更新"""
        if task_id in self.task_subscriptions:
            self.task_subscriptions[task_id].discard(websocket)

    async def broadcast_progress(self, progress: ProgressUpdate):
        """广播进度更新"""
        connections = self.task_subscriptions.get(progress.task_id, set())

        # 也发送给所有全局连接
        connections = connections.union(self.active_connections)

        disconnected = []
        for connection in connections:
            try:
                await connection.send_json(progress.model_dump())
            except Exception:
                disconnected.append(connection)

        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)


class APIServer:
    """API服务器"""

    VERSION = "1.0.0"
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 8787

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        """
        初始化API服务器

        Args:
            host: 监听地址，默认为 127.0.0.1
            port: 监听端口，默认为 8787
        """
        self.host = host or self.DEFAULT_HOST
        self.port = port or self.DEFAULT_PORT

        # 任务管理器
        self.task_manager = TaskManager()

        # WebSocket连接管理器
        self.connection_manager = ConnectionManager()

        # FastAPI应用
        self.app = self._create_app()

        # 服务器实例
        self._server = None

    def _create_app(self) -> FastAPI:
        """创建FastAPI应用"""

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """应用生命周期管理"""
            # 启动时
            await self.task_manager.start()
            logger.info(f"API服务器已启动: http://{self.host}:{self.port}")
            yield
            # 关闭时
            await self.task_manager.stop()
            logger.info("API服务器已关闭")

        app = FastAPI(
            title="VideoMind Bridge API",
            description="VideoMind Bridge 本地API服务，支持视频下载、转录、AI摘要生成",
            version=self.VERSION,
            lifespan=lifespan,
        )

        allowed_origins = [
            "chrome-extension://",
            "moz-extension://",
            "http://127.0.0.1",
            "http://localhost",
            "http://[::1]",
        ]

        @app.middleware("http")
        async def cors_middleware(request, call_next):
            origin = request.headers.get("origin", "")
            
            is_allowed = (
                not origin or
                any(origin.startswith(allowed) for allowed in allowed_origins)
            )
            
            response = await call_next(request)
            
            if is_allowed and origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
            
            return response

        @app.options("/{path:path}")
        async def options_handler(path: str):
            from fastapi.responses import Response
            return Response(status_code=200)

        # 注册路由
        self._register_routes(app)

        return app

    def _register_routes(self, app: FastAPI):
        """注册API路由"""

        @app.get("/", response_model=Dict)
        async def root():
            """根路径，返回API信息"""
            return {
                "name": "VideoMind Bridge API",
                "version": self.VERSION,
                "docs": "/docs",
                "health": "/health",
            }

        @app.get("/health", response_model=Dict)
        async def health():
            """健康检查"""
            return {
                "status": "healthy",
                "version": self.VERSION,
            }

        @app.get("/api/v1/status", response_model=SystemStatusResponse)
        async def get_status():
            """获取系统状态"""
            stats = self.task_manager.get_statistics()
            return SystemStatusResponse(
                version=self.VERSION,
                status="running",
                active_tasks=stats["active"],
                queued_tasks=stats["queued"],
                completed_tasks=stats["completed"],
                failed_tasks=stats["failed"],
            )

        @app.get("/api/v1/config", response_model=ConfigResponse)
        async def get_config():
            """获取系统配置"""
            ai_enabled = not self.task_manager._ai_service.mock
            return ConfigResponse(
                default_output_dir=str(self.task_manager.output_dir),
                supported_platforms=["bilibili", "youtube", "douyin", "xiaohongshu"],
                supported_ai_providers=["deepseek", "openai", "anthropic"],
                supported_export_targets=["local", "obsidian", "notion"],
                ai_enabled=ai_enabled,
            )

        # 任务管理API
        @app.post("/api/v1/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
        async def create_task(request: TaskCreateRequest):
            """创建新任务"""
            try:
                task = await self.task_manager.create_task(
                    url=str(request.url),
                    mode=request.mode,
                    targets=set(request.targets),
                    ai_provider=request.ai_provider,
                    ai_prompt=request.ai_prompt,
                    cookies_from_browser=request.cookies_from_browser,
                )

                # 注册进度回调
                self.task_manager.register_callback(
                    task.id,
                    lambda t: asyncio.create_task(self._on_task_update(t)),
                )

                return self._task_to_response(task)
            except Exception as e:
                logger.error(f"创建任务失败: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=str(e),
                )

        @app.get("/api/v1/tasks", response_model=TaskListResponse)
        async def list_tasks(
            status: Optional[TaskStatus] = None,
            limit: int = 20,
            offset: int = 0,
        ):
            """获取任务列表"""
            tasks = await self.task_manager.get_tasks(
                status=status,
                limit=limit,
                offset=offset,
            )
            total = len(self.task_manager._tasks)

            return TaskListResponse(
                total=total,
                tasks=[self._task_to_response(t) for t in tasks],
                page=offset // limit + 1,
                page_size=limit,
            )

        @app.get("/api/v1/tasks/{task_id}", response_model=TaskResponse)
        async def get_task(task_id: UUID):
            """获取单个任务"""
            task = await self.task_manager.get_task(task_id)
            if not task:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"任务不存在: {task_id}",
                )
            return self._task_to_response(task)

        @app.post("/api/v1/tasks/{task_id}/cancel")
        async def cancel_task(task_id: UUID):
            """取消任务"""
            success = await self.task_manager.cancel_task(task_id)
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"无法取消任务: {task_id}",
                )
            return {"success": True, "message": "任务已取消"}

        @app.delete("/api/v1/tasks/{task_id}")
        async def delete_task(task_id: UUID):
            """删除任务"""
            success = await self.task_manager.delete_task(task_id)
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"任务不存在: {task_id}",
                )
            return {"success": True, "message": "任务已删除"}

        # WebSocket端点
        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket连接，用于实时接收任务进度更新"""
            origin = websocket.headers.get("origin", "")
            
            allowed_origins = [
                "chrome-extension://",
                "moz-extension://",
                "http://127.0.0.1",
                "http://localhost",
                "http://[::1]",
            ]
            
            is_allowed = (
                not origin or
                any(origin.startswith(allowed) for allowed in allowed_origins)
            )
            
            if not is_allowed:
                logger.warning(f"WebSocket 连接被拒绝，Origin: {origin}")
                await websocket.close(code=1008)
                return
            
            await self.connection_manager.connect(websocket)
            try:
                while True:
                    # 接收客户端消息
                    data = await websocket.receive_json()

                    # 处理订阅请求
                    if data.get("action") == "subscribe":
                        task_id = UUID(data.get("task_id"))
                        self.connection_manager.subscribe_to_task(task_id, websocket)
                        await websocket.send_json({
                            "type": "subscribed",
                            "task_id": str(task_id),
                        })

                    elif data.get("action") == "unsubscribe":
                        task_id = UUID(data.get("task_id"))
                        self.connection_manager.unsubscribe_from_task(task_id, websocket)
                        await websocket.send_json({
                            "type": "unsubscribed",
                            "task_id": str(task_id),
                        })

            except WebSocketDisconnect:
                self.connection_manager.disconnect(websocket)
            except Exception as e:
                logger.error(f"WebSocket错误: {e}")
                self.connection_manager.disconnect(websocket)

    async def _on_task_update(self, task: VideoTask) -> None:
        """任务更新回调"""
        progress = ProgressUpdate(
            task_id=task.id,
            status=task.status,
            progress=task.progress,
            current_step=task.current_step,
            message=task.error_msg if task.status == TaskStatus.FAILED else None,
        )
        await self.connection_manager.broadcast_progress(progress)

    def _task_to_response(self, task: VideoTask) -> TaskResponse:
        """将VideoTask转换为TaskResponse"""
        return TaskResponse(
            id=task.id,
            url=task.url,
            status=task.status,
            mode=task.mode,
            targets=list(task.targets),
            progress=task.progress,
            current_step=task.current_step,
            title=task.metadata.title if task.metadata else None,
            author=task.metadata.author if task.metadata else None,
            platform=task.metadata.platform if task.metadata else None,
            created_at=task.created_at,
            updated_at=task.updated_at,
            completed_at=task.completed_at,
            error_msg=task.error_msg,
            summary=task.ai_summary,
            output_files=[str(p) for p in task.output_files],
        )

    async def start(self) -> None:
        """启动API服务器"""
        import uvicorn

        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        self._server = uvicorn.Server(config)
        await self._server.serve()

    async def stop(self) -> None:
        """停止API服务器"""
        if self._server:
            self._server.should_exit = True
