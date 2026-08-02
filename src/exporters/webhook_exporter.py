"""Webhook 导出器实现"""

import json
from datetime import datetime
from typing import Any

import httpx

from ..models.task import ExportContext, ExportResult, ExportTarget
from ..utils import get_logger
from .base import BaseExporter

logger = get_logger(__name__)


class WebhookExporter(BaseExporter):
    """Webhook 导出器 - 将处理结果推送到指定 URL"""

    name = "Webhook"
    icon = "🔗"

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        events: list | None = None
    ):
        """
        初始化 Webhook 导出器

        Args:
            url: Webhook 接收地址
            headers: 自定义 HTTP 请求头
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）
            events: 触发事件列表 ["on_completed", "on_failed"]
        """
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.events = events or ["on_completed"]

    def validate_config(self) -> tuple[bool, str]:
        """验证配置"""
        if not self.url:
            return False, "Webhook URL 未配置"

        if not self.url.startswith(('http://', 'https://')):
            return False, "Webhook URL 必须以 http:// 或 https:// 开头"

        return True, ""

    def export(self, context: ExportContext) -> ExportResult:
        """
        执行 Webhook 导出

        将处理结果以 JSON 格式 POST 到配置的 URL
        """
        # 验证配置
        valid, error = self.validate_config()
        if not valid:
            return ExportResult(
                success=False,
                target=ExportTarget.WEBHOOK,
                error_msg=error
            )

        # 构建 webhook 数据
        payload = self._build_payload(context)

        # 发送请求（带重试）
        success, error_msg, response_data = self._send_with_retry(payload)

        if success:
            logger.info(f"Webhook 发送成功: {self.url}")
            return ExportResult(
                success=True,
                target=ExportTarget.WEBHOOK,
                remote_url=self.url,
                metadata={
                    "response": response_data,
                    "timestamp": datetime.now().isoformat()
                }
            )
        else:
            logger.error(f"Webhook 发送失败: {error_msg}")
            return ExportResult(
                success=False,
                target=ExportTarget.WEBHOOK,
                error_msg=error_msg,
                metadata={
                    "timestamp": datetime.now().isoformat()
                }
            )

    def _build_payload(self, context: ExportContext) -> dict[str, Any]:
        """构建 Webhook 请求数据"""
        meta = context.video_metadata

        # 提取关键时间轴
        highlights = self._extract_highlights(context)

        # 构建输出文件信息
        output_files = {}
        if context.video_path:
            output_files["video"] = str(context.video_path)
        if context.audio_path:
            output_files["audio"] = str(context.audio_path)
        if context.transcript_path:
            output_files["transcript"] = str(context.transcript_path)

        payload = {
            "event": "video.processed",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "task_id": str(context.task_id),
                "url": meta.url,
                "status": "completed",
                "metadata": {
                    "title": meta.title,
                    "author": meta.author,
                    "platform": meta.platform,
                    "duration": meta.duration,
                    "thumbnail_url": meta.thumbnail_url,
                    "description": meta.description,
                },
                "summary": context.ai_summary,
                "transcript": context.transcript_text,
                "transcript_segments": [
                    {
                        "start": seg.start,
                        "end": seg.end,
                        "text": seg.text,
                        "confidence": seg.confidence
                    }
                    for seg in context.transcript_segments
                ] if context.transcript_segments else [],
                "highlights": highlights,
                "output_files": output_files,
                "config": {
                    "prompt_template_id": context.config.get("prompt_template_id"),
                    "processing_mode": context.config.get("processing_mode", "full")
                }
            }
        }

        return payload

    def _extract_highlights(self, context: ExportContext) -> list:
        """从上下文中提取关键时间轴"""
        highlights = []

        # 从 config 中提取 highlights
        if hasattr(context, 'config') and context.config:
            highlights_data = context.config.get("highlights", [])
            if highlights_data:
                for h in highlights_data:
                    if isinstance(h, dict):
                        highlights.append({
                            "time": h.get("time", ""),
                            "seconds": h.get("seconds", 0),
                            "content": h.get("content", "")
                        })

        return highlights

    def _send_with_retry(
        self,
        payload: dict[str, Any]
    ) -> tuple[bool, str, dict | None]:
        """
        发送 Webhook 请求（带重试机制）

        Returns:
            Tuple[bool, str, Optional[Dict]]: (成功, 错误信息, 响应数据)
        """
        import time

        # 准备请求头
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "VideoMind-Bridge/1.0",
            **self.headers
        }

        last_error = ""

        for attempt in range(self.max_retries):
            try:
                response = httpx.post(
                    self.url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                    follow_redirects=True
                )

                # 检查响应状态
                if response.status_code < 400:
                    # 尝试解析响应 JSON
                    try:
                        response_data = response.json()
                    except json.JSONDecodeError:
                        response_data = {"text": response.text}

                    return True, "", response_data
                else:
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                    logger.warning(f"Webhook 请求失败 (尝试 {attempt + 1}/{self.max_retries}): {last_error}")

            except httpx.TimeoutException:
                last_error = f"请求超时 ({self.timeout}秒)"
                logger.warning(f"Webhook 超时 (尝试 {attempt + 1}/{self.max_retries})")

            except httpx.ConnectError as e:
                last_error = f"连接错误: {str(e)}"
                logger.warning(f"Webhook 连接错误 (尝试 {attempt + 1}/{self.max_retries}): {e}")

            except Exception as e:
                last_error = f"请求异常: {str(e)}"
                logger.warning(f"Webhook 异常 (尝试 {attempt + 1}/{self.max_retries}): {e}")

            # 如果不是最后一次尝试，等待后重试
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay * (attempt + 1))  # 指数退避

        return False, f"重试 {self.max_retries} 次后仍然失败: {last_error}", None

    def should_trigger(self, event: str) -> bool:
        """检查是否应该触发指定事件"""
        return event in self.events

