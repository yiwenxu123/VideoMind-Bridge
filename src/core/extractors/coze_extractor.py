"""Coze 提取器适配器

封装现有 Coze 工作流代码为 ContentExtractor 接口。
复用 Hermes video-content-extractor skill 的 Coze 调用代码。

注意: Coze 不是必需的提取器。有 Token 时优先使用 (免费+快),
无 Token 或过期时 is_available() 返回 False, 自动跳过。
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import httpx

from ..models import CostTier, ExtractResult
from . import register_extractor
from .base import ContentExtractor

# 环境变量名称
ENV_COZE_FLOW_ID = "COZE_BOT_ID"  # Coze workflow/bot ID

# Coze API 端点
COZE_API_BASE = "https://api.coze.cn"
COZE_CHAT_URL = f"{COZE_API_BASE}/v1/chat"
COZE_MESSAGE_URL = f"{COZE_API_BASE}/v1/chat/message/list"
COZE_WORKFLOW_URL = f"{COZE_API_BASE}/v1/workflow/run"

# Coze 工作流 ID (从 .env 或环境变量读取)
_DEFAULT_WORKFLOW_ID = os.getenv(ENV_COZE_FLOW_ID, "")

# 支持的 URL 模式
_SUPPORTED_DOMAINS = [
    "bilibili.com", "b23.tv", "youtube.com", "youtu.be",
    "douyin.com", "iesdouyin.com", "xiaohongshu.com", "xhslink.com",
]


class CozeExtractor(ContentExtractor):
    """Coze 工作流提取器适配器

    配置要求 (环境变量):
    - COZE_API_KEY: Coze API Token (必需)
    - COZE_BOT_ID: 工作流/机器人 ID (可选, 有默认值)

    行为:
    - is_available(): COZE_API_KEY 存在且非空 → True
    - extract(): 调用 Coze chat API, 等待异步结果
    """

    platform_name = "coze"
    _cost_tier = CostTier.CHEAP
    url_pattern = re.compile("|".join(_SUPPORTED_DOMAINS))

    def __init__(self) -> None:
        key = self._resolve_api_key("coze")
        self._api_key = key.strip() if key and key.strip() else ""
        self._workflow_id = _DEFAULT_WORKFLOW_ID

    def is_available(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    def extract(self, url: str) -> ExtractResult:
        if not self.is_available():
            return ExtractResult(
                success=False, platform="coze", title="", content="",
                source="coze", url=url, cost_tier=CostTier.CHEAP,
                error="Coze API Key 未配置",
            )

        try:
            # 调用 Coze 工作流
            result = self._call_coze_workflow(url)

            if not result or result.get("success") is False:
                error_msg = result.get("msg", "Coze 工作流返回空结果") if result else "Coze 工作流无响应"
                return ExtractResult(
                    success=False, platform="coze", title="", content="",
                    source="coze", url=url, cost_tier=CostTier.CHEAP,
                    error=f"Coze 提取失败: {error_msg}",
                )

            # 解析 Coze 返回内容
            content = result.get("data", "") or result.get("content", "") or ""
            title = self._parse_title_from_result(content, url)

            return ExtractResult(
                success=True,
                platform="coze",
                title=title,
                content=content,
                source="coze",
                url=url,
                cost_tier=CostTier.CHEAP,
                metadata={"raw_result": result},
            )

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 401:
                return ExtractResult(
                    success=False, platform="coze", title="", content="",
                    source="coze", url=url, cost_tier=CostTier.CHEAP,
                    error="Coze Token 过期 (HTTP 401), 自动跳过到其他提取器",
                )
            return ExtractResult(
                success=False, platform="coze", title="", content="",
                source="coze", url=url, cost_tier=CostTier.CHEAP,
                error=f"Coze API HTTP {status}: {e}",
            )
        except httpx.TimeoutException:
            return ExtractResult(
                success=False, platform="coze", title="", content="",
                source="coze", url=url, cost_tier=CostTier.CHEAP,
                error="Coze 请求超时 (120s), 自动跳过到其他提取器",
            )
        except Exception as e:
            return ExtractResult(
                success=False, platform="coze", title="", content="",
                source="coze", url=url, cost_tier=CostTier.CHEAP,
                error=f"Coze 提取异常: {e}",
            )

    def _call_coze_workflow(self, url: str) -> dict[str, Any] | None:
        """调用 Coze 工作流 API

        参考: Hermes coze-workflow.md 的 chat API 流程
        """
        if self._workflow_id:
            return self._call_workflow_run(url)

        return self._call_chat_api(url)

    def _call_chat_api(self, url: str) -> dict[str, Any] | None:
        """通过 Coze Chat API 调用工作流"""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # 1. 创建聊天
        payload = {
            "bot_id": self._workflow_id,
            "user_id": "videomind-bridge",
            "query": f"请提取并整理这个视频的文字内容: {url}",
            "stream": False,
        }

        with httpx.Client(timeout=120.0) as client:
            chat_resp = client.post(
                f"{COZE_API_BASE}/v3/chat",
                headers=headers,
                json=payload,
            )
            chat_resp.raise_for_status()
            chat_data = chat_resp.json()

            if chat_data.get("code") != 0:
                msg = chat_data.get("msg", "unknown")
                raise RuntimeError(f"Coze chat API 错误: {msg}")

            chat_id = chat_data.get("data", {}).get("id", "")
            conversation_id = chat_data.get("data", {}).get("conversation_id", "")

            if not chat_id:
                return None

            # 2. 等待完成并获取消息
            # Coze chat 是异步的, 需要轮询
            for _ in range(60):  # 最多等 60 次
                status_resp = client.get(
                    f"{COZE_API_BASE}/v3/chat/{chat_id}",
                    headers=headers,
                    params={"conversation_id": conversation_id},
                )
                status_data = status_resp.json()
                chat_status = status_data.get("data", {}).get("status", "")

                if chat_status == "completed":
                    break
                elif chat_status in ("failed", "cancelled"):
                    return {"success": False, "msg": f"Coze chat status: {chat_status}"}

                time.sleep(2)
            else:
                return {"success": False, "msg": "Coze chat 超时"}

            # 3. 获取消息
            msg_resp = client.get(
                f"{COZE_API_BASE}/v3/chat/message/list",
                headers=headers,
                params={"chat_id": chat_id, "conversation_id": conversation_id},
            )
            msg_data = msg_resp.json()

            messages = msg_data.get("data", [])
            content_parts = []
            for msg in messages:
                if msg.get("role") == "assistant" and msg.get("content"):
                    content_parts.append(msg["content"])

            full_content = "\n".join(content_parts)
            return {
                "success": True,
                "data": full_content,
                "source": "coze_chat",
            }

    def _call_workflow_run(self, url: str) -> dict[str, Any] | None:
        """通过 Coze Workflow Run API (简化版, 同步)"""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "workflow_id": self._workflow_id,
            "parameters": json.dumps({"url": url}),
        }

        with httpx.Client(timeout=120.0) as client:
            resp = client.post(COZE_WORKFLOW_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                msg = data.get("msg", "unknown")
                # 401 Token 过期
                if resp.status_code == 401 or data.get("code") == 401:
                    return {"success": False, "msg": f"Token expired: {msg}"}
                return {"success": False, "msg": f"Coze workflow error: {msg}"}

            execute_data = data.get("data", {})
            return {
                "success": True,
                "data": execute_data.get("output", ""),
                "source": "coze_workflow",
            }

    @staticmethod
    def _parse_title_from_result(content: str, url: str) -> str:
        """从 Coze 返回结果中解析标题"""
        lines = content.strip().split("\n")
        for line in lines[:10]:
            line = line.strip()
            if line and len(line) > 5 and len(line) < 200 and not line.startswith(("http", "#", "---")):
                return line
        return f"Coze 提取结果 ({url})"


register_extractor("coze", CozeExtractor)
