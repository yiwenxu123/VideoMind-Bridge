"""API服务器

基于FastAPI的REST API和WebSocket服务。
"""

import asyncio
import os
import time
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ..core.metrics import get_api_metrics
from ..core.models import SCHEMA_VERSION, CostTier
from ..services.config_manager import ConfigManager
from ..utils import get_logger
from .models import (
    ConfigResponse,
    ExtractResponse,
    KeyGroup,
    KeysListResponse,
    KeyUpdateRequest,
    SettingsResponse,
    SettingsUpdateRequest,
    SystemStatusResponse,
)

logger = get_logger(__name__)

# 本机放行主机名 (精确匹配, 不做前缀/子串匹配)
_LOCAL_ORIGINS = {"127.0.0.1", "localhost", "::1"}
# 浏览器扩展 Origin 无可仿冒主机位, 按 scheme 放行 (兼容任意扩展 ID)
_EXTENSION_SCHEMES = {"chrome-extension", "moz-extension", "safari-web-extension"}


def _is_allowed_origin(origin: str) -> bool:
    """Origin 精确校验。

    修复历史缺陷: 旧实现用 origin.startswith("http://127.0.0.1") 前缀匹配,
    http://127.0.0.1.evil.com 这类仿冒源可绕过 CSRF 防线。
    """
    if not origin:
        return True  # 非浏览器客户端不带 Origin
    try:
        parsed = urllib.parse.urlsplit(origin)
    except ValueError:
        return False
    scheme = parsed.scheme.lower()
    if scheme in _EXTENSION_SCHEMES:
        return True
    if scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()  # hostname 已去除 IPv6 方括号
    return host in _LOCAL_ORIGINS


def _require_admin_consumer(request: Request) -> None:
    """配置面写操作的角色检查: 多消费者模式下仅 admin 可用。

    consumer 由鉴权中间件写入 request.state; 未启用鉴权 (本地模式) 时放行。
    """
    if not getattr(request.state, "vmb_auth_enabled", False):
        return
    if getattr(request.state, "consumer", None) != "admin":
        raise HTTPException(status_code=403, detail="该操作需要 admin token")


def _resolve_request_asr_chain(payload: dict) -> list[str] | None:
    """解析请求里的 asr / asr_chain 覆盖，返回链或 None。

    asr: 首选后端，失败后继续默认链；asr_chain: 严格按给定链执行。
    """
    from ..core.asr import validate_chain
    from ..core.asr.types import AsrConfigError

    raw_chain = payload.get("asr_chain")
    if raw_chain is not None:
        if (
            not isinstance(raw_chain, list)
            or not raw_chain
            or not all(isinstance(name, str) and name.strip() for name in raw_chain)
        ):
            raise HTTPException(status_code=400, detail="asr_chain 必须是非空字符串数组")
        chain = [name.strip() for name in raw_chain]
        try:
            validate_chain(chain)
        except AsrConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return chain

    raw_asr = payload.get("asr")
    if raw_asr is not None:
        if not isinstance(raw_asr, str) or not raw_asr.strip():
            raise HTTPException(status_code=400, detail="asr 必须是非空字符串")
        backend = raw_asr.strip()
        try:
            validate_chain([backend])
        except AsrConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        default_chain = ConfigManager().get_asr_config().chain
        return [backend] + [name for name in default_chain if name != backend]

    return None


def _parse_cost_tier(payload: dict) -> tuple[CostTier, str]:
    """解析 cost_tier，并回报它从哪来。

    返回 (tier, source)：source 为 "request"（调用方显式传了）或 "default"
    （服务端按 CHEAP 处理）。2026-11-25 起这个来源会回显在响应里 ——
    服务端替调用方做花钱决策这件事必须可见，不能静默。
    """
    raw = payload.get("cost_tier")
    if raw is None:
        return CostTier.CHEAP, "default"
    try:
        return CostTier(str(raw).strip().lower()), "request"
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="cost_tier 必须是 free/cheap/paid/expensive/premium",
        ) from exc


def _build_extract_options(payload: dict, request_id: str):
    """把请求参数转成 ExtractOptions，非法参数返回 400。"""
    from ..core.models import CostTier, ExtractOptions

    chain = _resolve_request_asr_chain(payload)

    asr_options = payload.get("asr_options") or {}
    if not isinstance(asr_options, dict):
        raise HTTPException(status_code=400, detail="asr_options 必须是对象")
    language = asr_options.get("language")
    if language is not None and not isinstance(language, str):
        raise HTTPException(status_code=400, detail="asr_options.language 必须是字符串")

    max_cost = None
    raw_max_cost = payload.get("asr_max_cost")
    if raw_max_cost is not None:
        try:
            max_cost = CostTier(str(raw_max_cost).strip().lower())
        except ValueError:
            raise HTTPException(status_code=400, detail="asr_max_cost 非法")

    return ExtractOptions(
        asr_chain=chain,
        asr_language=language,
        asr_max_cost=max_cost,
        request_id=request_id,
    )


def _extract_response(result, request_id: str, cost_tier_source: str = "default") -> dict:
    """构造 /extract 响应（只增不减：保留旧字段并补契约字段）。"""
    payload = {
        "success": result.success,
        "schema_version": SCHEMA_VERSION,
        "platform": result.platform,
        "title": result.title,
        "content": result.content,
        "language": result.language,
        "duration_seconds": result.duration_seconds,
        "cost_tier": result.cost_tier.value,
        "cost_tier_source": cost_tier_source,
        "source": result.source,
        "url": result.url,
        "completeness": result.completeness,
        "method": result.method,
        "request_id": request_id or result.request_id,
    }
    if result.segments:
        payload["segments"] = result.segments
    if result.asr_provider:
        payload["asr"] = {
            "provider": result.asr_provider,
            "model": result.asr_model,
            "model_version": result.asr_model_version,
        }
    # 2026-11-21: 暴露逐提取器的失败明细（extractor / error_code / error）。
    # 之前只回最后一个提取器的 error，调用方无法判断"抖音网关没起"还是"视频不可见"。
    attempts = (result.metadata or {}).get("attempts")
    if attempts:
        payload["attempts"] = attempts
    if result.error:
        payload["error"] = result.error
    if result.error_code:
        payload["error_code"] = result.error_code
    return payload


class APIServer:
    """API服务器"""

    VERSION = "3.0.0"
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 8787

    def __init__(self, host: str | None = None, port: int | None = None):
        """
        初始化API服务器

        Args:
            host: 监听地址，默认为 127.0.0.1
            port: 监听端口，默认为 8787
        """
        self.host = host or self.DEFAULT_HOST
        self.port = port or self.DEFAULT_PORT

        # 可选鉴权：admin token + 多消费者 token；未配置时保持本地无鉴权模式
        from .auth import AuthConfig, RateLimiter

        self._auth = AuthConfig.from_env()
        self._rate_limiter = RateLimiter(self._auth.rate_limit_per_min)
        self._api_token = self._auth.admin_token

        # 长生命周期 Router（缓存/提取器/HTTP 连接复用）
        from ..core.router_runtime import RouterRuntime
        self._router_runtime = RouterRuntime()

        # 启动即校验 ASR 默认链，坏配置不拖到第一次转写才暴露
        from ..core.asr import validate_configured_chain

        try:
            validate_configured_chain()
        except Exception as exc:
            raise RuntimeError(f"ASR 配置非法: {exc}") from exc

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
            logger.info(f"API服务器已启动: http://{self.host}:{self.port}")
            try:
                yield
            finally:
                self._router_runtime.close()
                logger.info("API服务器已关闭")

        app = FastAPI(
            title="VideoMind Bridge API",
            description="VideoMind Bridge 本地API服务，多平台内容提取与转写（v1 流水线已于 2026-11-25 移除）",
            version=self.VERSION,
            lifespan=lifespan,
        )

        from ..core.discovery.config import comments_enabled, creator_feed_enabled
        creator_feed_is_enabled = creator_feed_enabled()
        comments_is_enabled = comments_enabled()

        @app.middleware("http")
        async def security_middleware(request, call_next):
            started = time.perf_counter()
            consumer = None
            # 2026-11-23：默认未启用鉴权时 consumer 一直是 None，导致**完全没有调用记录**，
            # 想收敛工具面/端点数全凭猜。这里改为无论如何都解析一个调用方标识：
            # 鉴权通过的 consumer 优先，其次 X-Consumer-Id 请求头，最后记 anonymous。
            declared_consumer = request.headers.get("x-consumer-id", "").strip()
            request.state.vmb_auth_enabled = self._auth.enabled
            origin = request.headers.get("origin", "")

            is_allowed = _is_allowed_origin(origin)

            # 默认关闭的 Discovery 端点显式返回 404，避免被 OPTIONS 通配路由变成 405
            request_path = request.url.path.rstrip("/")
            if (
                not creator_feed_is_enabled
                and request_path == "/api/v1/creator/feed"
            ):
                return JSONResponse(status_code=404, content={"detail": "Not Found"})
            if not comments_is_enabled and request_path == "/api/v1/comments":
                return JSONResponse(status_code=404, content={"detail": "Not Found"})

            # CSRF 防护: 带非白名单 Origin 的请求直接拒绝 (而非仅不返回 CORS 头)
            if not is_allowed:
                logger.warning(f"请求被拒绝，非法 Origin: {origin} {request.url.path}")
                return JSONResponse(status_code=403, content={"detail": "非法 Origin"})

            # 鉴权: 配置了 admin/消费者 token 时, /api/v1 需携带 Bearer token
            if self._auth.enabled and request.url.path.startswith("/api/v1") and request.method != "OPTIONS":
                consumer = self._auth.authenticate(request.headers.get("authorization", ""))
                if consumer is None:
                    logger.info(
                        f"api_access consumer=anonymous method={request.method} "
                        f"path={request.url.path} status=401 "
                        f"duration_ms={round((time.perf_counter() - started) * 1000, 1)}"
                    )
                    return JSONResponse(status_code=401, content={"detail": "未授权"})
                request.state.consumer = consumer

                allowed, retry_after = self._rate_limiter.allow(consumer)
                if not allowed:
                    logger.info(
                        f"api_access consumer={consumer} method={request.method} "
                        f"path={request.url.path} status=429 "
                        f"duration_ms={round((time.perf_counter() - started) * 1000, 1)}"
                    )
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "请求过于频繁", "consumer": consumer},
                        headers={"Retry-After": str(max(1, int(retry_after) + 1))},
                    )

            response = await call_next(request)

            # 总是记录调用方（此前只在启用鉴权时记录 → 本机等于零可见性）
            if request.url.path.startswith("/api/v1"):
                who = consumer or declared_consumer or "anonymous"
                logger.info(
                    f"api_access consumer={who} method={request.method} "
                    f"path={request.url.path} status={response.status_code} "
                    f"duration_ms={round((time.perf_counter() - started) * 1000, 1)}"
                )
                # 记成指标：跑一周就能拿到"谁在调哪些端点"的真实清单，
                # 这是收敛工具面/端点的依据（而不是靠猜）。
                get_api_metrics().record(
                    who, request.method, request.url.path, response.status_code
                )

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

        from .session_routes import router as session_router
        app.include_router(session_router)

        from .metrics_routes import router as metrics_router
        app.include_router(metrics_router)

        # Discovery API 默认关闭；开启后才注册对应路由
        if creator_feed_is_enabled or comments_is_enabled:
            from .discovery_routes import include_discovery_routes
            include_discovery_routes(app)

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
            """默认入口：Gateway Console。"""
            return RedirectResponse(url="/console", status_code=302)

        @app.get("/console")
        @app.get("/console/")
        async def console():
            """Gateway 控制台（只读观测 + 提取/评论操作）。"""
            from pathlib import Path as _Path
            index = (
                _Path(__file__).resolve().parent.parent.parent
                / "web"
                / "console"
                / "index.html"
            )
            if index.is_file():
                return FileResponse(str(index))
            return JSONResponse(
                content={"message": "Gateway Console 未找到"},
                status_code=404,
            )

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
            # 2026-11-25（A2）：v1 任务队列已删除，四个计数恒为 0。
            # 保留字段是为了不破坏已按这四列写代码的调用方（CONTRACT §2 把它列为稳定端点）。
            # 代码里没有任何执行者 —— 0 是事实（没有任务在跑），不是占位。
            return SystemStatusResponse(
                version=self.VERSION,
                status="running",
                active_tasks=0,
                queued_tasks=0,
                completed_tasks=0,
                failed_tasks=0,
            )

        @app.get("/api/v1/capabilities", response_model=dict)
        async def get_capabilities():
            """能力发现：ASR 后端 + 平台提取器（不加载模型）"""
            from ..core.capabilities import capabilities_payload

            return capabilities_payload(
                extractor_status=self._router_runtime.extractor_status()
            )

        @app.get("/api/v1/config", response_model=ConfigResponse)
        async def get_config():
            """获取系统配置"""
            config_mgr = ConfigManager()
            cfg = config_mgr.config
            return ConfigResponse(
                default_output_dir=cfg.download.output_dir,
                supported_platforms=["bilibili", "youtube", "douyin", "xiaohongshu", "local"],
                supported_export_targets=["local", "obsidian", "html_player"],
            )

        # v2 提取 API
        # exclude_unset：进什么键出什么键。默认模式会给未出现的字段补 null（成功路径 +5 个、
        # 内部异常信封 +14 个），对做「key 是否存在」判断的消费者等同于改形状。
        @app.post("/api/v1/extract", response_model=ExtractResponse, response_model_exclude_unset=True)
        async def extract_content(request: dict):
            """快速提取视频内容 (v2 引擎)"""
            url = request.get("url")
            if not url:
                raise HTTPException(status_code=400, detail="url 不能为空")

            request_id = uuid4().hex
            try:
                options = _build_extract_options(request, request_id)
                cost_tier, cost_tier_source = _parse_cost_tier(request)
                result = self._router_runtime.extract(
                    url,
                    max_cost=cost_tier,
                    options=options,
                )
                return _extract_response(result, request_id, cost_tier_source)
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"v2 提取失败: {e}")
                return {
                    "success": False,
                    "url": url,
                    "error": str(e),
                    "schema_version": SCHEMA_VERSION,
                    "request_id": request_id,
                    "error_code": "internal_error",
                    "cost_tier_source": "default",
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

                from src.core import HermesFormatter
                from src.core.archiver import ArchiverConfig, archive_extract_result

                cost_tier, cost_tier_source = _parse_cost_tier(request)
                result = self._router_runtime.extract(url, max_cost=cost_tier)

                if not result.success or not result.content.strip():
                    # 2026-11-24：失败必须带可机读 error_code（CONTRACT.md 不变式 1）。
                    # 之前这里只回人类可读 error，下游无法按原因分流。
                    return {
                        "success": False,
                        "url": url,
                        "error": result.error or "提取失败, 无真实内容",
                        "error_code": result.error_code or "extract_failed",
                        "cost_tier_source": cost_tier_source,
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
                    "cost_tier_source": cost_tier_source,
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
                return {
                    "success": False,
                    "url": url,
                    "error": str(e),
                    "error_code": "internal_error",
                    "cost_tier_source": "default",
                }

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

        @app.post("/api/v1/prescreen")
        async def prescreen(body: dict):
            """零网络的成本/价值预筛（不下载视频）。

            2026-11-24 新增：此前预筛只存在于 MCP 工具里，REST 没有对应端点。
            补上之后 MCP 才能做成"薄适配器统一走 :8787"，不用在 MCP 进程里再跑一遍引擎。
            """
            url = body.get("url")
            if not url:
                raise HTTPException(status_code=400, detail="url 不能为空")

            from ..core.prescreen_api import run_prescreen

            return run_prescreen(
                self._router_runtime, str(url), str(body.get("mode") or "quick")
            )

        # 提取器 API Key 管理
        @app.get("/api/v1/keys", response_model=KeysListResponse)
        async def list_keys():
            """列出所有提取器 API Key 的配置状态"""
            config_mgr = ConfigManager()
            groups = config_mgr.list_extractor_key_status()
            return {"groups": {k: KeyGroup(**v) for k, v in groups.items()}}

        @app.put("/api/v1/keys")
        async def set_key(request: KeyUpdateRequest, http_request: Request):
            """设置提取器 API Key"""
            _require_admin_consumer(http_request)
            config_mgr = ConfigManager()
            ok = config_mgr.set_extractor_key(request.name, request.value)
            if not ok:
                raise HTTPException(status_code=400, detail="Key 名无效或值为空")
            logger.info(f"提取器 Key 已设置: {request.name}")
            return {"success": True, "name": request.name}

        @app.delete("/api/v1/keys/{name}")
        async def delete_key(name: str, http_request: Request):
            """删除提取器 API Key"""
            _require_admin_consumer(http_request)
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

        # 平台登录态 (session) 管理: 写操作仅 admin (只读视图见 session_routes GET /sessions)
        @app.put("/api/v1/sessions/settings/{key}")
        async def set_session(key: str, http_request: Request, body: dict):
            """设置平台登录态 (key 形如 bilibili:cookies_file / ytdlp:browser)"""
            _require_admin_consumer(http_request)
            config_mgr = ConfigManager()
            if key not in config_mgr.SESSION_KEYS:
                raise HTTPException(
                    status_code=400,
                    detail=f"未知会话键: {key}，有效值: {', '.join(sorted(config_mgr.SESSION_KEYS))}",
                )
            value = str(body.get("value") or "").strip()
            if not value:
                raise HTTPException(status_code=400, detail="value 不能为空")
            if key.endswith(":cookies_file"):
                expanded = Path(value).expanduser()
                if not expanded.is_file():
                    raise HTTPException(status_code=400, detail=f"cookies 文件不存在: {expanded}")
                value = str(expanded)
            if not config_mgr.set_session_setting(key, value):
                raise HTTPException(status_code=500, detail="设置失败")
            logger.info(f"会话设置已更新: {key}")
            return {"success": True, "key": key}

        @app.delete("/api/v1/sessions/settings/{key}")
        async def delete_session(key: str, http_request: Request):
            """删除平台登录态设置"""
            _require_admin_consumer(http_request)
            config_mgr = ConfigManager()
            if key not in config_mgr.SESSION_KEYS:
                raise HTTPException(status_code=400, detail=f"未知会话键: {key}")
            ok = config_mgr.delete_session_setting(key)
            if not ok:
                raise HTTPException(status_code=404, detail="设置不存在或删除失败")
            logger.info(f"会话设置已删除: {key}")
            return {"success": True, "key": key}

        # 设置 API
        @app.get("/api/v1/settings", response_model=SettingsResponse)
        async def get_settings():
            """获取当前设置"""
            config_mgr = ConfigManager()
            config_mgr.reload()
            cfg = config_mgr.config
            return SettingsResponse(
                output_dir=cfg.download.output_dir,
                obsidian_enabled=cfg.export.obsidian.enabled,
                obsidian_vault_path=cfg.export.obsidian.vault_path,
                obsidian_subfolder=cfg.export.obsidian.subfolder,
            )

        @app.put("/api/v1/settings")
        async def update_settings(request: SettingsUpdateRequest, http_request: Request):
            """更新设置（2026-11-25 A2 后：只接受仍有执行者的项）"""
            _require_admin_consumer(http_request)
            config_mgr = ConfigManager()
            changed: list[str] = []

            if request.output_dir is not None:
                config_mgr.update_download(output_dir=request.output_dir)
                changed.append("output_dir")

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
            logger.info(f"设置已更新: {', '.join(changed) or '无变化'}")
            return {"success": True, "updated": changed}

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
