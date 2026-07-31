"""MCP Server - 为 AI Agent 提供视频处理能力

基于 Model Context Protocol (MCP)，通过 stdio 传输 JSON-RPC 消息。
任何支持 MCP 的 Agent（Claude Desktop、OpenClaw、Cursor 等）可发现并调用。

启动方式:
    python -m src.mcp.server
"""

import json
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.models.task import ExportTarget, ProcessingMode
from src.services.ai_service import AIService
from src.services.download_service import DownloadService
from src.services.export_orchestrator import ExportOrchestrator
from src.services.transcribe_service import TranscribeService
from src.utils import get_logger

logger = get_logger(__name__)

OUTPUT_DIR = Path.home() / "Downloads" / "VideoMind"


class MCPServer:
    def __init__(self):
        self._services: dict[str, Any] = {}
        self._initialized = False

    def _get_service(self, name: str, factory: Callable):
        if name not in self._services:
            self._services[name] = factory()
        return self._services[name]

    def _send(self, data: dict):
        line = json.dumps(data, ensure_ascii=False)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def _send_error(self, req_id: Any, code: int, message: str):
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        })

    def _send_result(self, req_id: Any, result: Any):
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result,
        })

    def _send_tool_result(self, req_id: Any, result: dict):
        """工具调用成功响应 (MCP CallToolResult 规范: content 数组 + isError)"""
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                **result,  # 平铺兼容字段, 便于旧客户端直接读取
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "isError": False,
            },
        })

    def _send_tool_error(self, req_id: Any, message: str):
        """工具调用失败响应 (MCP 规范: 返回 isError:true 的 result, 而非 JSON-RPC error)"""
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": message}],
                "isError": True,
            },
        })

    def _handle_initialize(self, req_id: Any):
        self._initialized = True
        self._send_result(req_id, {
            "protocolVersion": "2025-03-26",
            "capabilities": {
                "tools": {},
                "resources": {},
            },
            "serverInfo": {
                "name": "VideoMind Bridge",
                "version": "1.0.0",
            },
        })

    def _handle_tools_list(self, req_id: Any):
        self._send_result(req_id, {
            "tools": [
                {
                    "name": "videomind_process",
                    "description": "完整处理视频：下载→转录→AI摘要→导出",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "视频链接"},
                            "mode": {
                                "type": "string",
                                "enum": ["full", "download", "transcribe"],
                                "description": "处理模式（默认 full）",
                            },
                            "targets": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "导出目标列表（local, obsidian）",
                            },
                            "whisper_model": {
                                "type": "string",
                                "enum": ["tiny", "base", "small", "medium"],
                                "description": "Whisper 模型大小（默认 small）",
                            },
                            "cookie_browser": {
                                "type": "string",
                                "description": "浏览器名称（chrome/safari/firefox，国内平台需要）",
                            },
                        },
                        "required": ["url"],
                    },
                },
                {
                    "name": "videomind_download",
                    "description": "仅下载视频/音频",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "视频链接"},
                            "keep_video": {
                                "type": "boolean",
                                "description": "是否保留视频文件（默认 true）",
                            },
                            "cookie_browser": {"type": "string"},
                        },
                        "required": ["url"],
                    },
                },
                {
                    "name": "videomind_transcribe",
                    "description": "仅转录音频生成 SRT 字幕",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "audio_path": {"type": "string", "description": "音频文件路径"},
                            "whisper_model": {"type": "string"},
                            "language": {"type": "string", "description": "语言代码（默认 zh）"},
                        },
                        "required": ["audio_path"],
                    },
                },
                {
                    "name": "videomind_supported",
                    "description": "检查 URL 是否为支持的视频平台",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "要检查的视频链接"},
                        },
                        "required": ["url"],
                    },
                },
                {
                    "name": "extract_video",
                    "description": "提取视频/内容的文字内容。智能路由: Coze(优先,免费积分)→平台API→yt-dlp+ASR, 自动降级。返回标题+正文+来源。",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "视频/内容链接，支持抖音/B站/小红书/YouTube"},
                            "cost_tier": {
                                "type": "string",
                                "enum": ["free", "cheap", "paid", "expensive", "premium"],
                                "description": "最大可接受成本等级 (默认 cheap, 允许使用 Coze 免费积分)",
                            },
                        },
                        "required": ["url"],
                    },
                },
                {
                    "name": "smart_extract",
                    "description": "智能提取: 先预筛内容质量(规则引擎)，再按等级自动决定是否值得提取。低于C级自动跳过避免浪费配额。适合批量处理前的快速决策。",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "视频/内容链接"},
                            "max_cost": {
                                "type": "string",
                                "enum": ["free", "cheap", "paid", "expensive", "premium"],
                                "description": "最大成本等级 (默认: 根据预筛等级自动推荐)",
                            },
                            "min_grade": {
                                "type": "string",
                                "enum": ["S", "A", "B", "C", "D"],
                                "description": "最低可接受等级 (默认 C)",
                            },
                        },
                        "required": ["url"],
                    },
                },
                {
                    "name": "prescreen_video",
                    "description": "预筛视频内容质量。纯规则引擎零网络请求。根据URL/标题/时长评分(0-100)返回S/A/B/C/D等级。适合先判断内容是否值得处理或用于批量过滤。",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "视频/内容链接"},
                            "mode": {
                                "type": "string",
                                "enum": ["quick", "full"],
                                "description": "quick=仅URL分析(<2ms), full=先提取元信息再评分(<10s)",
                            },
                        },
                        "required": ["url"],
                    },
                },
                {
                    "name": "list_extractors",
                    "description": "列出所有可用的内容提取器及其状态、优先级、成本等级",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                    },
                },
                {
                    "name": "videomind_config",
                    "description": "获取当前系统配置和平台支持信息",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                    },
                },
                {
                    "name": "configure",
                    "description": "设置/查看 VideoMind API Keys。支持的 key: coze (Coze API Token), coze_ali_key (ASR用阿里云Key), tikhub, apify, aliyun_access_key_id/secret/appkey",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["get", "set"],
                                "description": "get=读取, set=设置",
                            },
                            "key": {
                                "type": "string",
                                "description": "set 时必填: coze / coze_ali_key / tikhub / apify / aliyun_access_key_id / secret / appkey",
                            },
                            "value": {
                                "type": "string",
                                "description": "set 时必填",
                            },
                        },
                        "required": ["action"],
                    },
                },
            ],
        })

    def _handle_tools_call(self, req_id: Any, params: dict):
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        handler = {
            "videomind_process": self._call_process,
            "videomind_download": self._call_download,
            "videomind_transcribe": self._call_transcribe,
            "videomind_supported": self._call_supported,
            "videomind_config": self._call_config,
            "configure": self._call_configure,
            "prescreen_video": self._call_prescreen_video,
            "smart_extract": self._call_smart_extract,
            "extract_video": self._call_extract_video,
            "list_extractors": self._call_list_extractors,
        }.get(name)

        if not handler:
            self._send_error(req_id, -32601, f"Unknown tool: {name}")
            return

        try:
            result = handler(arguments)
            self._send_tool_result(req_id, result)
        except Exception as e:
            logger.error(f"Tool call failed: {name}: {e}")
            self._send_tool_error(req_id, str(e))

    def _call_process(self, args: dict) -> dict:
        url = args["url"]
        mode = args.get("mode", "full")
        targets = args.get("targets", ["local", "obsidian"])
        whisper_model = args.get("whisper_model", "small")
        cookie_browser = args.get("cookie_browser")

        output_dir = OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        download_service = DownloadService(output_dir)
        transcribe_service = TranscribeService(model_size=whisper_model)
        ai_service = AIService()

        target_map = {
            "local": ExportTarget.LOCAL,
            "obsidian": ExportTarget.OBSIDIAN,
            "notion": ExportTarget.NOTION,
            "webhook": ExportTarget.WEBHOOK,
        }
        target_enums = [target_map.get(t, ExportTarget.LOCAL) for t in targets]
        processing_mode = {
            "full": ProcessingMode.FULL,
            "download": ProcessingMode.DOWNLOAD_ONLY,
            "transcribe": ProcessingMode.TRANSCRIBE_ONLY,
        }[mode]

        result = download_service.download(
            url, download_video=True, cookies_from_browser=cookie_browser,
        )

        if processing_mode == ProcessingMode.DOWNLOAD_ONLY:
            return {
                "success": True,
                "mode": "download",
                "title": result.metadata.title,
                "author": result.metadata.author,
                "duration": result.metadata.duration,
                "platform": result.metadata.platform,
                "audio_path": str(result.audio_path) if result.audio_path else None,
                "video_path": str(result.video_path) if result.video_path else None,
            }

        transcript = transcribe_service.transcribe(result.audio_path, language="zh")

        if processing_mode == ProcessingMode.TRANSCRIBE_ONLY:
            return {
                "success": True,
                "mode": "transcribe",
                "title": result.metadata.title,
                "language": transcript.language,
                "segments_count": len(transcript.segments),
                "full_text": transcript.formatted_text,
                "audio_path": str(result.audio_path),
            }

        summary = ai_service.summarize(
            transcript=transcript.formatted_text,
            title=result.metadata.title,
        )

        from src.models.task import ExportContext
        context = ExportContext(
            task_id=uuid.uuid4(),
            video_metadata=result.metadata,
            video_path=result.video_path,
            audio_path=result.audio_path,
            transcript_segments=transcript.segments,
            transcript_text=transcript.formatted_text,
            ai_summary=summary.summary,
        )

        orchestrator = ExportOrchestrator(
            targets=list(target_enums),
            config={"local_output_path": output_dir},
        )
        export_results = orchestrator.export_all(context)

        return {
            "success": True,
            "mode": "full",
            "title": result.metadata.title,
            "author": result.metadata.author,
            "duration": result.metadata.duration,
            "platform": result.metadata.platform,
            "transcript": {
                "language": transcript.language,
                "segments_count": len(transcript.segments),
            },
            "summary": {
                "text": summary.summary,
                "highlights": [
                    {"time": h.time, "seconds": h.seconds, "content": h.content}
                    for h in (summary.highlights or [])
                ],
            },
            "exports": [
                {
                    "target": r.target.value,
                    "success": r.success,
                    "output_path": str(r.output_path) if r.output_path else None,
                }
                for r in export_results
            ],
        }

    def _call_download(self, args: dict) -> dict:
        url = args["url"]
        keep_video = args.get("keep_video", True)
        cookie_browser = args.get("cookie_browser")

        output_dir = OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        download_service = DownloadService(output_dir)
        result = download_service.download(
            url, download_video=keep_video, cookies_from_browser=cookie_browser,
        )

        return {
            "success": True,
            "title": result.metadata.title,
            "author": result.metadata.author,
            "duration": result.metadata.duration,
            "platform": result.metadata.platform,
            "audio_path": str(result.audio_path) if result.audio_path else None,
            "video_path": str(result.video_path) if result.video_path else None,
        }

    def _call_transcribe(self, args: dict) -> dict:
        audio_path = Path(args["audio_path"])
        whisper_model = args.get("whisper_model", "small")
        language = args.get("language", "zh")

        transcribe_service = TranscribeService(model_size=whisper_model)
        transcript = transcribe_service.transcribe(audio_path, language=language)

        return {
            "success": True,
            "language": transcript.language,
            "language_probability": transcript.language_probability,
            "segments_count": len(transcript.segments),
            "full_text": transcript.formatted_text,
        }

    def _call_supported(self, args: dict) -> dict:
        url = args["url"]
        download_service = DownloadService(OUTPUT_DIR)
        supported = download_service.is_supported(url)
        platform = download_service._detect_platform(url)

        return {
            "url": url,
            "supported": supported,
            "platform": platform,
        }

    def _call_configure(self, args: dict) -> dict:
        action = args.get("action", "get")

        from src.services.config_manager import ConfigManager

        config_mgr = ConfigManager()

        if action == "set":
            key = args.get("key", "")
            value = args.get("value", "")

            if not key or not value:
                return {"success": False, "error": "set 模式需要 key 和 value 参数", "action": "set"}

            valid_names = set(config_mgr.EXTRACTOR_PROVIDERS.keys())
            if key not in valid_names:
                return {
                    "success": False,
                    "error": f"未知配置键: {key}。有效键名: {', '.join(sorted(valid_names))}",
                    "action": "set",
                }

            ok = config_mgr.set_extractor_key(key, value)
            if not ok:
                return {"success": False, "error": f"设置失败: {key}", "action": "set"}

            logger.info(f"MCP configure set: {key}")
            return {"success": True, "action": "set", "key": key, "message": f"{key} 已设置"}

        # get 模式
        key_status = config_mgr.list_extractor_key_status()
        total_extractors = len(config_mgr.EXTRACTOR_GROUPS)
        return {
            "success": True,
            "action": "get",
            "config": {
                "output_dir": str(Path.home() / "Downloads" / "VideoMind"),
                "extractors_available": sum(
                    1 for g in key_status.values() if g["all_configured"]
                ),
                "total_extractors": total_extractors,
                "extractor_keys": key_status,
            },
        }

    def _call_prescreen_video(self, args: dict) -> dict:
        """执行内容预筛"""
        url = args["url"]
        mode = args.get("mode", "quick")

        from src.core import ContentRouter, Prescreener

        router = ContentRouter()
        prescreener = Prescreener(router)

        if mode == "full":
            from src.core.models import CostTier
            # 先用 FREE 成本提取元信息
            quick_result = router.extract(url, max_cost=CostTier.FREE)
            if quick_result.success and quick_result.title:
                result = prescreener.prescreen(
                    url,
                    title=quick_result.title,
                    duration_seconds=quick_result.duration_seconds,
                )
            else:
                result = prescreener.prescreen_quick(url)
        else:
            result = prescreener.prescreen_quick(url)

        return {
            "url": result.url,
            "platform": result.platform,
            "grade": result.grade.value,
            "score": round(result.score, 1),
            "title": result.title,
            "duration_seconds": result.duration_seconds,
            "reasons": result.reasons,
            "metadata": result.metadata,
        }

    def _call_smart_extract(self, args: dict) -> dict:
        """智能提取: 预筛 + 自动提取"""
        url = args["url"]
        max_cost_str = args.get("max_cost")
        min_grade_str = args.get("min_grade", "C")

        from src.core import ContentRouter, HermesFormatter, Prescreener
        from src.core.models import ContentGrade, CostTier

        grade_map = {"S": ContentGrade.S, "A": ContentGrade.A, "B": ContentGrade.B, "C": ContentGrade.C, "D": ContentGrade.D}
        cost_map = {
            "free": CostTier.FREE, "cheap": CostTier.CHEAP,
            "paid": CostTier.PAID, "expensive": CostTier.EXPENSIVE,
            "premium": CostTier.PREMIUM,
        }

        min_grade = grade_map.get(min_grade_str, ContentGrade.C)
        max_cost = cost_map.get(max_cost_str) if max_cost_str else None

        router = ContentRouter()
        prescreener = Prescreener(router)

        # 1. 先用 FREE 成本获取元信息做预筛
        quick_result = router.extract(url, max_cost=CostTier.FREE)
        if quick_result.success and quick_result.title:
            prescreen_result = prescreener.prescreen(
                url,
                title=quick_result.title,
                duration_seconds=quick_result.duration_seconds,
            )
        else:
            prescreen_result = prescreener.prescreen_quick(url)

        # 2. 判断是否值得提取
        is_worth = prescreener.is_extraction_worthwhile(prescreen_result.grade, min_grade)

        # 3. 提取 (如值得)
        extract_output = None
        if is_worth:
            # FREE 提取已拿到完整内容时直接复用, 避免重复提取
            if quick_result.success and quick_result.content.strip() and not quick_result.is_placeholder:
                extract_result = quick_result
            else:
                # FREE 失败/仅占位时, 按推荐成本二次提取 (缓存中无成功结果, 不会命中)
                if max_cost is None:
                    recommended = prescreener.recommend_cost_tier(prescreen_result.grade)
                    max_cost = cost_map.get(recommended, CostTier.FREE)
                extract_result = router.extract(url, max_cost=max_cost)
            if extract_result.success and extract_result.content.strip() and not extract_result.is_placeholder:
                extract_output = HermesFormatter.format_extract_result_full(extract_result)

        # 4. 合并输出
        return {
            "success": True,
            "url": url,
            "prescreen": {
                "grade": prescreen_result.grade.value,
                "score": round(prescreen_result.score, 1),
                "reasons": prescreen_result.reasons,
                "extraction_recommended": is_worth,
            },
            "extraction_performed": is_worth,
            "extraction_skipped": not is_worth,
            "skip_reason": f"预筛 {prescreen_result.grade.value} 级, 低于 {min_grade_str} 级阈值" if not is_worth else None,
            "result": extract_output,
        }

    def _call_extract_video(self, args: dict) -> dict:
        url = args["url"]
        cost_tier_str = args.get("cost_tier", "cheap")

        from src.core import ContentRouter, HermesFormatter
        from src.core.models import CostTier

        cost_map = {
            "free": CostTier.FREE, "cheap": CostTier.CHEAP,
            "paid": CostTier.PAID, "expensive": CostTier.EXPENSIVE,
            "premium": CostTier.PREMIUM,
        }
        max_cost = cost_map.get(cost_tier_str)

        router = ContentRouter()
        result = router.extract(url, max_cost=max_cost)
        return HermesFormatter.format_extract_result_full(result)

    def _call_list_extractors(self, _args: dict) -> dict:
        from src.core import ContentRouter
        router = ContentRouter()
        return router.list_extractors()

    def _call_config(self, _args: dict) -> dict:
        import yt_dlp
        ies = {type(ie).__name__ for ie in yt_dlp.extractor.gen_extractors()}
        platforms = []
        for name in ["YouTube", "Bilibili", "Douyin", "XiaoHongShu", "TikTok", "Weibo", "Zhihu"]:
            platforms.append({
                "name": name,
                "available": f"{name}IE" in ies or f"{name}VideoIE" in ies or name == "Douyin",
            })

        return {
            "output_dir": str(OUTPUT_DIR),
            "whisper_models": ["tiny", "base", "small", "medium"],
            "export_targets": ["local", "obsidian", "notion", "webhook"],
            "platforms": platforms,
        }

    def handle_message(self, msg: dict):
        req_id = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params", {})

        if method == "initialize":
            self._handle_initialize(req_id)
        elif method == "notifications/initialized":
            self._initialized = True
        elif method == "ping":
            self._send_result(req_id, {})
        elif method == "tools/list":
            self._handle_tools_list(req_id)
        elif method == "tools/call":
            self._handle_tools_call(req_id, params)
        elif method == "resources/list":
            self._send_result(req_id, {"resources": []})
        elif method == "resources/read":
            self._send_result(req_id, {"contents": []})
        elif method == "notifications/cancelled":
            pass
        else:
            if req_id is not None:
                self._send_error(req_id, -32601, f"Method not found: {method}")

    def run(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                self.handle_message(msg)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
            except Exception as e:
                logger.error(f"Handler error: {e}")


def main():
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
