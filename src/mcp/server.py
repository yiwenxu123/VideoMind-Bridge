"""MCP Server - 为 AI Agent 提供视频处理能力

基于 Model Context Protocol (MCP)，通过 stdio 传输 JSON-RPC 消息。
任何支持 MCP 的 Agent（Claude Desktop、OpenClaw、Cursor 等）可发现并调用。

启动方式:
    python -m src.mcp.server
"""

import json
import sys
import time
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from src.models.task import ProcessingMode, ExportTarget, Highlight
from src.services.download_service import DownloadService
from src.services.transcribe_service import TranscribeService
from src.services.ai_service import AIService
from src.services.export_orchestrator import ExportOrchestrator
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
                    "name": "videomind_config",
                    "description": "获取当前系统配置信息",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                    },
                },
                {
                    "name": "extract_video",
                    "description": "提取视频文字内容 (v2 引擎, 多提取器自动降级)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "视频/内容链接"},
                            "cost_tier": {
                                "type": "string",
                                "enum": ["free", "cheap", "paid", "expensive", "premium"],
                                "description": "最大可接受成本等级 (默认 free)",
                            },
                        },
                        "required": ["url"],
                    },
                },
                {
                    "name": "list_extractors",
                    "description": "列出所有可用的内容提取器及其状态",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
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
            "extract_video": self._call_extract_video,
            "list_extractors": self._call_list_extractors,
        }.get(name)

        if not handler:
            self._send_error(req_id, -32601, f"Unknown tool: {name}")
            return

        try:
            result = handler(arguments)
            self._send_result(req_id, result)
        except Exception as e:
            logger.error(f"Tool call failed: {name}: {e}")
            self._send_error(req_id, -32603, str(e))

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

        from src.models.task import ExportContext, VideoMetadata
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
            targets=set(target_enums),
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

    def _call_extract_video(self, args: dict) -> dict:
        url = args["url"]
        cost_tier_str = args.get("cost_tier", "free")

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

    def _call_list_extractors(self, args: dict) -> dict:
        from src.core import ContentRouter
        router = ContentRouter()
        return router.list_extractors()

    def _call_config(self, args: dict) -> dict:
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
        self._send({
            "jsonrpc": "2.0",
            "method": "server/initialized",
            "params": {},
        })

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
