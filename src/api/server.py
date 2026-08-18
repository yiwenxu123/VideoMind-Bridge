"""API服务器

基于FastAPI的REST API和WebSocket服务。
"""

import asyncio
import os
from contextlib import asynccontextmanager, suppress
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..models.task import ProcessingMode, TaskStatus, VideoTask
from ..services.config_manager import ConfigManager
from ..utils import get_logger
from .models import (
    ConfigResponse,
    KeyGroup,
    KeysListResponse,
    KeyUpdateRequest,
    ProgressUpdate,
    SettingsResponse,
    SettingsUpdateRequest,
    SystemStatusResponse,
    TaskCreateRequest,
    TaskListResponse,
    TaskResponse,
)
from .task_manager import TaskManager

logger = get_logger(__name__)


class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.task_subscriptions: dict[UUID, set[WebSocket]] = {}

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
        for _task_id, connections in self.task_subscriptions.items():
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
        subscriptions = self.task_subscriptions.get(progress.task_id, set())
        all_targets = set(self.active_connections) | subscriptions

        logger.debug(f"WebSocket广播: {progress.task_id}, 连接数={len(all_targets)}")

        data = progress.model_dump(mode="json")

        dead = set()
        for conn in all_targets:
            try:
                await conn.send_json(data)
            except Exception as e:
                logger.warning(f"  → 发送失败: {conn.client} - {e}")
                dead.add(conn)

        if dead:
            for conn in dead:
                if conn in self.active_connections:
                    self.active_connections.remove(conn)
                for subs in self.task_subscriptions.values():
                    subs.discard(conn)


class APIServer:
    """API服务器"""

    VERSION = "3.0.0"
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 8787

    # 允许的浏览器 Origin (前缀匹配, 兼容任意浏览器扩展 ID)
    ALLOWED_ORIGINS = [
        "chrome-extension://",
        "moz-extension://",
        "http://127.0.0.1",
        "http://localhost",
        "http://[::1]",
    ]

    def __init__(self, host: str | None = None, port: int | None = None):
        """
        初始化API服务器

        Args:
            host: 监听地址，默认为 127.0.0.1
            port: 监听端口，默认为 8787
        """
        self.host = host or self.DEFAULT_HOST
        self.port = port or self.DEFAULT_PORT

        # 可选鉴权 token: 设置 VIDEOMIND_API_TOKEN 后 /api/v1 需携带 Bearer token
        self._api_token = os.environ.get("VIDEOMIND_API_TOKEN", "")

        # 任务管理器
        self.task_manager = TaskManager()

        # WebSocket连接管理器
        self.connection_manager = ConnectionManager()

        # 事件循环引用（用于线程间调度）
        self._event_loop: Any = None

        # FastAPI应用
        self.app = self._create_app()

        # 服务器实例
        self._server: Any = None

    def _create_app(self) -> FastAPI:
        """创建FastAPI应用"""

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """应用生命周期管理"""
            self._event_loop = asyncio.get_running_loop()
            await self.task_manager.start()
            logger.info(f"API服务器已启动: http://{self.host}:{self.port}")
            yield
            await self.task_manager.stop()
            logger.info("API服务器已关闭")

        app = FastAPI(
            title="VideoMind Bridge API",
            description="VideoMind Bridge 本地API服务，支持视频下载、转录、AI摘要生成",
            version=self.VERSION,
            lifespan=lifespan,
        )

        allowed_origins = self.ALLOWED_ORIGINS

        @app.middleware("http")
        async def security_middleware(request, call_next):
            origin = request.headers.get("origin", "")

            is_allowed = (
                not origin or
                any(origin.startswith(allowed) for allowed in allowed_origins)
            )

            # CSRF 防护: 带非白名单 Origin 的请求直接拒绝 (而非仅不返回 CORS 头)
            if not is_allowed:
                logger.warning(f"请求被拒绝，非法 Origin: {origin} {request.url.path}")
                return JSONResponse(status_code=403, content={"detail": "非法 Origin"})

            # 鉴权: 配置了 token 时, /api/v1 需携带 Bearer token
            if self._api_token and request.url.path.startswith("/api/v1") and request.method != "OPTIONS":
                auth = request.headers.get("authorization", "")
                if auth != f"Bearer {self._api_token}":
                    return JSONResponse(status_code=401, content={"detail": "未授权"})

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

        # 挂载静态文件 (Web UI) — 基于文件位置解析, 不依赖 CWD
        from pathlib import Path as _Path
        web_dir = _Path(__file__).resolve().parent.parent.parent / "web"
        if web_dir.is_dir():
            app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

        # 挂载音频中转目录 (供 DashScope ASR 拉取)
        from .parse_service import get_media_dir
        media_dir = get_media_dir()
        media_dir.mkdir(parents=True, exist_ok=True)
        app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")

        return app

    def _register_routes(self, app: FastAPI):
        """注册API路由"""

        @app.get("/")
        async def root():
            """Web UI 首页"""
            from pathlib import Path as _Path
            web_dir = _Path(__file__).resolve().parent.parent.parent / "web"
            index = web_dir / "index.html"
            if index.is_file():
                return FileResponse(str(index))
            return JSONResponse(content={"message": "Web UI 未找到, 请从项目根目录启动"})

        @app.get("/health", response_model=dict)
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
            ai_enabled = self.task_manager.is_ai_available()
            return ConfigResponse(
                default_output_dir=str(self.task_manager.output_dir),
                supported_platforms=["bilibili", "youtube", "douyin", "xiaohongshu"],
                supported_ai_providers=["deepseek", "zhipu", "moonshot", "minimax", "doubao", "ollama"],
                supported_export_targets=["local", "obsidian", "notion"],
                ai_enabled=ai_enabled,
            )

        # v2 提取 API
        @app.post("/api/v1/extract")
        async def extract_content(request: dict):
            """快速提取视频内容 (v2 引擎)"""
            url = request.get("url")
            if not url:
                raise HTTPException(status_code=400, detail="url 不能为空")

            try:
                from src.core import ContentRouter
                from src.core.models import CostTier

                router = ContentRouter()
                result = router.extract(url, max_cost=CostTier.CHEAP)

                if result.success:
                    return {
                        "success": True,
                        "platform": result.platform,
                        "title": result.title,
                        "content": result.content,
                        "language": result.language,
                        "duration_seconds": result.duration_seconds,
                        "cost_tier": result.cost_tier.value,
                        "source": result.source,
                        "url": url,
                    }
                else:
                    return {
                        "success": False,
                        "error": result.error,
                        "url": url,
                    }
            except Exception as e:
                logger.error(f"v2 提取失败: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "url": url,
                }

        # v2 提取 + 归档 API
        @app.post("/api/v1/extract/archive")
        async def extract_and_archive(request: dict):
            """提取并归档 (v2): 提取全文 → 写入 Obsidian/本地/HTML"""
            url = request.get("url")
            if not url:
                raise HTTPException(status_code=400, detail="url 不能为空")
            targets = request.get("targets") or ["obsidian", "local"]
            obsidian_vault = request.get("obsidian_vault")
            obsidian_subfolder = request.get("obsidian_subfolder", "Inbox/Videos")
            local_output = request.get("local_output")

            try:
                from pathlib import Path

                from src.core import ContentRouter, HermesFormatter
                from src.core.archiver import ArchiverConfig, archive_extract_result
                from src.core.models import CostTier

                router = ContentRouter()
                result = router.extract(url, max_cost=CostTier.CHEAP)

                if not result.success or not result.content.strip():
                    return {
                        "success": False,
                        "url": url,
                        "error": result.error or "提取失败, 无真实内容",
                    }

                config = ArchiverConfig(
                    obsidian_vault_path=Path(obsidian_vault) if obsidian_vault else None,
                    obsidian_subfolder=obsidian_subfolder,
                    local_output_path=Path(local_output) if local_output else None,
                )
                archive_results = archive_extract_result(result, list(targets), config)

                return {
                    "success": True,
                    "url": url,
                    "extract": HermesFormatter.format_extract_result_full(result),
                    "archive": [
                        {
                            "success": r.success,
                            "target": r.target.value,
                            "output_path": str(r.output_path) if r.output_path else None,
                            "error": r.error_msg,
                        }
                        for r in archive_results
                    ],
                }
            except Exception as e:
                logger.error(f"v2 提取归档失败: {e}")
                return {"success": False, "url": url, "error": str(e)}

        # 视频源地址解析 (B站官方 playurl, 绕云 IP 风控)
        @app.post("/api/v1/parse")
        async def parse_video(request: Request, body: dict):
            """解析视频 URL → 下载音频 → 中转目录, 返回公网可访问的 voice_url

            供外部工作流调用, 下游接 DashScope ASR。
            """
            url = body.get("url")
            if not url:
                raise HTTPException(status_code=400, detail="url 不能为空")

            from .parse_service import parse_audio_source

            result = parse_audio_source(
                url,
                cookie_browser=body.get("cookie_browser"),
                cookies_file=body.get("cookies_file") or os.environ.get("VMB_COOKIES_FILE"),
            )

            if not result.get("success"):
                return {"success": False, "url": url, "error": result.get("error")}

            base_url = os.environ.get(
                "VMB_PUBLIC_BASE_URL",
                f"{request.url.scheme}://{request.url.netloc}",
            )
            return {
                "success": True,
                "url": url,
                "voice_url": f"{base_url}{result['path']}",
                "title": result.get("title", ""),
                "duration": result.get("duration", 0),
                "platform": result.get("platform", ""),
                "ext": result.get("ext", ""),
                "size_bytes": result.get("size_bytes", 0),
                "source": result.get("source", "unknown"),
            }

        # 提取器 API Key 管理
        @app.get("/api/v1/keys", response_model=KeysListResponse)
        async def list_keys():
            """列出所有提取器 API Key 的配置状态"""
            config_mgr = ConfigManager()
            groups = config_mgr.list_extractor_key_status()
            return {"groups": {k: KeyGroup(**v) for k, v in groups.items()}}

        @app.put("/api/v1/keys")
        async def set_key(request: KeyUpdateRequest):
            """设置提取器 API Key"""
            config_mgr = ConfigManager()
            ok = config_mgr.set_extractor_key(request.name, request.value)
            if not ok:
                raise HTTPException(status_code=400, detail="Key 名无效或值为空")
            logger.info(f"提取器 Key 已设置: {request.name}")
            return {"success": True, "name": request.name}

        @app.delete("/api/v1/keys/{name}")
        async def delete_key(name: str):
            """删除提取器 API Key"""
            valid_names = set(ConfigManager().EXTRACTOR_PROVIDERS.keys())
            if name not in valid_names:
                raise HTTPException(
                    status_code=400,
                    detail=f"未知 Key: {name}，有效值: {', '.join(sorted(valid_names))}",
                )
            config_mgr = ConfigManager()
            ok = config_mgr.delete_extractor_key(name)
            if not ok:
                raise HTTPException(status_code=500, detail="删除失败")
            logger.info(f"提取器 Key 已删除: {name}")
            return {"success": True, "name": name}

        # 设置 API
        @app.get("/api/v1/settings", response_model=SettingsResponse)
        async def get_settings():
            """获取当前设置"""
            config_mgr = ConfigManager()
            config_mgr.reload()
            cfg = config_mgr.config
            api_key = config_mgr.get_api_key()
            return SettingsResponse(
                ai_engine=cfg.ai.engine.value if hasattr(cfg.ai.engine, 'value') else str(cfg.ai.engine),
                ai_model=cfg.ai.model,
                ai_base_url=cfg.ai.base_url,
                ai_api_key_configured=bool(api_key),
                ai_temperature=cfg.ai.temperature,
                ai_max_tokens=cfg.ai.max_tokens,
                ai_timeout=cfg.ai.timeout,
                output_dir=cfg.download.output_dir,
                download_quality=cfg.download.video_quality,
                whisper_model=cfg.transcribe.whisper_model,
                save_srt=cfg.export.local.save_srt,
                save_transcript=cfg.export.local.save_transcript,
                save_markdown=cfg.export.local.save_markdown,
                obsidian_enabled=cfg.export.obsidian.enabled,
                obsidian_vault_path=cfg.export.obsidian.vault_path,
                obsidian_subfolder=cfg.export.obsidian.subfolder,
                available_engines=["DeepSeek-V3", "Ollama"],
            )

        @app.put("/api/v1/settings")
        async def update_settings(request: SettingsUpdateRequest):
            """更新设置"""
            config_mgr = ConfigManager()
            changed = []

            # AI 设置
            if request.ai_engine is not None:
                from ..models.config import AIEngine
                engine_val = request.ai_engine
                with suppress(ValueError):
                    engine_val = AIEngine(request.ai_engine)
                config_mgr.update_ai(engine=engine_val)
                changed.append("ai_engine")
            if request.ai_model is not None:
                config_mgr.update_ai(model=request.ai_model)
                changed.append("ai_model")
            if request.ai_base_url is not None:
                config_mgr.update_ai(base_url=request.ai_base_url)
                changed.append("ai_base_url")
            if request.ai_api_key is not None:
                config_mgr.set_api_key(request.ai_api_key)
                changed.append("ai_api_key")
            if request.ai_temperature is not None:
                config_mgr.update_ai(temperature=request.ai_temperature)
                changed.append("ai_temperature")
            if request.ai_max_tokens is not None:
                config_mgr.update_ai(max_tokens=request.ai_max_tokens)
                changed.append("ai_max_tokens")
            if request.ai_timeout is not None:
                config_mgr.update_ai(timeout=request.ai_timeout)
                changed.append("ai_timeout")

            # 下载设置
            if request.output_dir is not None:
                config_mgr.update_download(output_dir=request.output_dir)
                changed.append("output_dir")
            if request.download_quality is not None:
                config_mgr.update_download(video_quality=request.download_quality)
                changed.append("download_quality")

            # 转录设置
            if request.whisper_model is not None:
                config_mgr._config.transcribe.whisper_model = request.whisper_model
                changed.append("whisper_model")

            # 导出设置
            if request.save_srt is not None:
                config_mgr._config.export.local.save_srt = request.save_srt
                changed.append("save_srt")
            if request.save_transcript is not None:
                config_mgr._config.export.local.save_transcript = request.save_transcript
                changed.append("save_transcript")
            if request.save_markdown is not None:
                config_mgr._config.export.local.save_markdown = request.save_markdown
                changed.append("save_markdown")

            # Obsidian 导出设置
            obsidian_updates: dict[str, Any] = {}
            if request.obsidian_enabled is not None:
                obsidian_updates["enabled"] = request.obsidian_enabled
                changed.append("obsidian_enabled")
            if request.obsidian_vault_path is not None:
                obsidian_updates["vault_path"] = request.obsidian_vault_path
                changed.append("obsidian_vault_path")
            if request.obsidian_subfolder is not None:
                obsidian_updates["subfolder"] = request.obsidian_subfolder
                changed.append("obsidian_subfolder")
            if obsidian_updates:
                config_mgr.update_export(obsidian=obsidian_updates)

            config_mgr.save()

            logger.info(f"设置已更新: {', '.join(changed)}")
            return {"success": True, "updated": changed}

        @app.post("/api/v1/settings/test-ai")
        async def test_ai_connection():
            """测试 AI 连接"""
            config_mgr = ConfigManager()
            api_key = config_mgr.get_api_key()
            cfg = config_mgr.config

            if not api_key:
                return {"success": False, "message": "请先配置 API Key"}

            try:
                from ..services.ai_service import AIService
                ai = AIService(
                    api_key=api_key,
                    base_url=cfg.ai.base_url,
                    model=cfg.ai.model,
                    temperature=cfg.ai.temperature,
                    max_tokens=cfg.ai.max_tokens,
                )
                loop = asyncio.get_running_loop()
                ok, msg = await loop.run_in_executor(None, ai.test_connection)
                return {"success": ok, "message": msg if not ok else "AI 连接正常"}
            except Exception as e:
                logger.error(f"AI 连接测试失败: {e}")
                return {"success": False, "message": str(e)}

        # 任务管理API
        @app.post("/api/v1/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
        async def create_task(request: TaskCreateRequest):
            """创建新任务"""
            try:
                # 检查 AI 配置
                if (
                    request.mode == ProcessingMode.FULL
                    and not self.task_manager.is_ai_available()
                    and not request.allow_downgrade
                ):
                    raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=(
                                "AI 服务未配置，无法进行完整处理。"
                                "请在设置中配置 API Key，"
                                "或设置 allow_downgrade=true 降级为转录存档模式"
                            ),
                        )

                task = await self.task_manager.create_task(
                    url=str(request.url),
                    mode=request.mode,
                    targets=set(request.targets),
                    ai_provider=request.ai_provider,
                    ai_prompt=request.ai_prompt,
                    cookies_from_browser=request.cookies_from_browser,
                    allow_downgrade=request.allow_downgrade,
                )

                # 注册进度回调
                self.task_manager.register_callback(
                    task.id,
                    self._sync_on_task_update,
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
            status: TaskStatus | None = None,
            limit: int = Query(20, ge=1, le=100),
            offset: int = Query(0, ge=0),
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

            is_allowed = (
                not origin or
                any(origin.startswith(allowed) for allowed in self.ALLOWED_ORIGINS)
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

    def _sync_on_task_update(self, task: VideoTask) -> None:
        """同步包装器，将 async 回调调度到事件循环"""
        loop = getattr(self, '_event_loop', None)
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self._on_task_update(task), loop)
        else:
            logger.warning(f"WebSocket回调: 事件循环不可用 (loop={loop is not None}, running={loop.is_running() if loop else False})")

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
