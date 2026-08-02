"""Coze 提取器适配器 — Coze 优先策略

使用 Coze 工作流提取视频内容。支持三种模式:

模式 A (推荐): 平台专用工作流
  自动识别 URL 平台, 使用 skill 已验证的专用工作流 + stream_run SSE 端点。
  抖音 → 7645116403896385562, B站 → 7545785780040564799, 小红书 → 7545776707971039241

模式 B: 自定义工作流 (COZE_BOT_ID)
  设置 COZE_BOT_ID 环境变量覆盖, 使用同步 run 端点。

模式 C: Chat API (无工作流配置时兜底)
  通过 v3/chat 端点 Bot 对话提取内容。

配置要求 (环境变量):
  - COZE_API_KEY 或 COZE_API_TOKEN: 必需
  - COZE_BOT_ID: 可选, 覆盖自定义工作流
  - ALI_API_KEY: 可选, 传递到平台工作流做 ASR 兜底
  - COZE_DAILY_LIMIT: 可选, 每日调用上限 (默认 200)
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import date
from typing import Any

import httpx

from ...utils import get_logger
from ..models import CostTier, ExtractResult
from . import register_extractor
from .base import ContentExtractor

logger = get_logger(__name__)

# ── 平台专用工作流注册表 (来自已验证的 skill) ────────────────────

PLATFORM_WORKFLOWS: dict[str, dict[str, Any]] = {
    "douyin": {
        "workflow_id": "7645116403896385562",
        "params_fn": lambda url, ali_key: {"input": url, "ali_api": ali_key or ""},
        "response_format": "json",
    },
    "bilibili": {
        "workflow_id": "7545785780040564799",
        "params_fn": lambda url, ali_key: {"url": url, "ali_api_key": ali_key or ""},
        "response_format": "text",
    },
    "xiaohongshu": {
        "workflow_id": "7545776707971039241",
        "params_fn": lambda url, ali_key: {"url": url, "ali_aip_key": ali_key or ""},
        "response_format": "text",
    },
}

# ── 环境变量 ──────────────────────────────────────────────

ENV_COZE_FLOW_ID = "COZE_BOT_ID"
ENV_COZE_DAILY_LIMIT = "COZE_DAILY_LIMIT"
ENV_ALI_API_KEY = "ALI_API_KEY"

# Coze API 端点
COZE_API_BASE = "https://api.coze.cn"
COZE_WORKFLOW_URL = f"{COZE_API_BASE}/v1/workflow/run"
COZE_STREAM_RUN_URL = f"{COZE_API_BASE}/v1/workflow/stream_run"

# 支持的 URL 模式
_SUPPORTED_DOMAINS = [
    "bilibili.com", "b23.tv", "youtube.com", "youtu.be",
    "douyin.com", "iesdouyin.com", "xiaohongshu.com", "xhslink.com",
]


# ── 平台识别 ──────────────────────────────────────────────

def identify_platform(url: str) -> str:
    """委托统一的平台检测器 (单一来源)"""
    from ...utils.platform_detector import detect_platform
    return detect_platform(url)


# ── SSE 响应解析 ─────────────────────────────────────────

def _content_is_error(text: str) -> bool:
    text = text.strip()
    if not text:
        return True
    error_patterns = (
        "失败", "错误", "error", "fail", "exception",
        "transcription_url", "Invalid", "invalid",
    )
    return any(p in text.lower() for p in error_patterns) and len(text) < 200


def _parse_sse_response(raw_data: str, response_format: str, platform: str) -> dict[str, Any] | None:
    for line in raw_data.split("\n"):
        if line.startswith("data:") and '"node_title":"End"' in line:
            try:
                event_data = json.loads(line[5:].strip())
                content = event_data.get("content", "")
                usage = event_data.get("usage", {}) or {}
                token_count = usage.get("token_count", 0)

                # 仅当既无内容又无 token 时才跳过 (工作流可能不上报 usage, 但有内容仍应返回)
                if token_count == 0 and not content:
                    continue

                if response_format == "json" and platform == "douyin":
                    data = json.loads(content) if isinstance(content, str) and content.startswith("{") else content
                    if isinstance(data, dict):
                        output1 = data.get("output1", {})
                        if isinstance(output1, dict):
                            text = output1.get("text", "") or data.get("output", "")
                            desc = output1.get("desc", "") or data.get("desc", "")
                            if text and not _content_is_error(text):
                                return {
                                    "success": True,
                                    "title": desc,
                                    "content": text,
                                    "source": f"coze_{platform}",
                                }
                        text = data.get("output", "") or data.get("text", "")
                        if text and not _content_is_error(text):
                            return {
                                "success": True,
                                "title": data.get("desc", ""),
                                "content": text,
                                "source": f"coze_{platform}",
                            }
                        # JSON 对象存在但内容为空 → 工作流未提取到内容
                        return None

                if response_format == "text":
                    title = ""
                    title_match = re.search(r"标题[：:](.*?)(?:\n|$)", content)
                    if title_match:
                        title = title_match.group(1).strip()
                    body_match = re.search(r"正文[：:](.*)", content, re.DOTALL)
                    body = body_match.group(1).strip() if body_match else content
                    if not _content_is_error(body):
                        return {
                            "success": True,
                            "title": title,
                            "content": body,
                            "source": f"coze_{platform}",
                        }

                if content and not _content_is_error(content):
                    return {
                        "success": True,
                        "title": "",
                        "content": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False),
                        "source": f"coze_{platform}",
                    }

            except (json.JSONDecodeError, AttributeError):
                continue

    return None


class CozeExtractor(ContentExtractor):
    """Coze 提取器 (全平台, 优先使用免费每日积分)"""

    platform_name = "coze"
    _cost_tier = CostTier.CHEAP
    url_pattern = re.compile("|".join(_SUPPORTED_DOMAINS))

    # 每日调用配额 (类级别共享, 线程锁保护)
    _call_count: int = 0
    _call_date: str = ""
    _quota_lock = threading.Lock()

    def __init__(self) -> None:
        key = self._resolve_api_key("coze") or self._resolve_api_key("coze_token")
        self._api_key = key.strip() if key and key.strip() else ""
        self._workflow_id = os.getenv(ENV_COZE_FLOW_ID, "")
        ali_key = self._resolve_api_key("coze_ali_key") or os.getenv(ENV_ALI_API_KEY, "")
        self._ali_api_key = ali_key.strip() if ali_key and ali_key.strip() else ""

        # 延迟读取配额上限, 支持运行期修改; 非法值回退默认 200
        raw_limit = os.getenv(ENV_COZE_DAILY_LIMIT, "200")
        try:
            self._daily_limit = int(raw_limit)
        except ValueError:
            logger.warning(f"COZE_DAILY_LIMIT 非法值: {raw_limit!r}, 使用默认 200")
            self._daily_limit = 200

    def is_available(self) -> bool:
        return bool(self._api_key)

    def extract(self, url: str) -> ExtractResult:

        if not self.is_available():
            return ExtractResult(
                success=False, platform="coze", title="", content="",
                source="coze", url=url, cost_tier=CostTier.CHEAP,
                error="Coze API Key 未配置",
            )

        # 检查每日配额
        if not self._check_quota():
            return ExtractResult(
                success=False, platform="coze", title="", content="",
                source="coze", url=url, cost_tier=CostTier.CHEAP,
                error=f"Coze 每日调用量已达上限 ({self._daily_limit}), 自动跳过",
            )

        try:
            result = self._call_coze(url)

            if not result or result.get("success") is False:
                error_msg = result.get("msg", "Coze 工作流返回空结果") if result else "Coze 工作流无响应"
                if any(kw in error_msg.lower() for kw in ("balance", "quota", "insufficient", "limit", "积分")):
                    self._mark_quota_exhausted(error_msg)
                return ExtractResult(
                    success=False, platform="coze", title="", content="",
                    source="coze", url=url, cost_tier=CostTier.CHEAP,
                    error=f"Coze 提取失败: {error_msg}",
                )

            content = result.get("content", "") or result.get("data", "") or ""
            if not content.strip():
                return ExtractResult(
                    success=False, platform="coze", title="", content="",
                    source="coze", url=url, cost_tier=CostTier.CHEAP,
                    error="Coze 提取失败: 内容为空",
                )

            title = result.get("title", "") or self._parse_title_from_result(content, url)

            return ExtractResult(
                success=True,
                platform=result.get("source_platform", "coze"),
                title=title,
                content=content,
                source=result.get("source", "coze"),
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
                    error="Coze Token 过期 (HTTP 401), 自动跳过",
                )
            if status == 402:
                self._mark_quota_exhausted("402 Payment Required")
                return ExtractResult(
                    success=False, platform="coze", title="", content="",
                    source="coze", url=url, cost_tier=CostTier.CHEAP,
                    error="Coze 积分耗尽 (HTTP 402), 自动跳过",
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
                error="Coze 请求超时 (60s), 自动跳过",
            )
        except Exception as e:
            return ExtractResult(
                success=False, platform="coze", title="", content="",
                source="coze", url=url, cost_tier=CostTier.CHEAP,
                error=f"Coze 提取异常: {e}",
            )

    # ── 配额管理 ──────────────────────────────────────

    def _check_quota(self) -> bool:
        """检查是否还有配额 (不预扣)"""
        today = str(date.today())
        with CozeExtractor._quota_lock:
            if CozeExtractor._call_date != today:
                CozeExtractor._call_date = today
                CozeExtractor._call_count = 0
            return not CozeExtractor._call_count >= self._daily_limit

    def _count_call(self) -> None:
        """在真实 API 调用后计数 (线程安全)"""
        today = str(date.today())
        with CozeExtractor._quota_lock:
            if CozeExtractor._call_date != today:
                CozeExtractor._call_date = today
                CozeExtractor._call_count = 0
            CozeExtractor._call_count += 1

    def _mark_quota_exhausted(self, _reason: str) -> None:
        with CozeExtractor._quota_lock:
            CozeExtractor._call_count = self._daily_limit
            CozeExtractor._call_date = str(date.today())

    # ── API 调用 ──────────────────────────────────────

    def _call_coze(self, url: str) -> dict[str, Any] | None:
        """调用 Coze: 平台工作流 → 自定义工作流, 均不支持时让路由器降级"""
        platform = identify_platform(url)

        if self._workflow_id:
            return self._call_workflow_run(self._workflow_id, {"url": url})

        if platform in PLATFORM_WORKFLOWS:
            return self._call_platform_workflow(url, platform)

        return None

    def _call_platform_workflow(self, url: str, platform: str) -> dict[str, Any] | None:
        """调用平台专用工作流 (stream_run SSE)"""
        config = PLATFORM_WORKFLOWS[platform]
        workflow_id = config["workflow_id"]
        params = config["params_fn"](url, self._ali_api_key)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "workflow_id": workflow_id,
            "parameters": params,
        }

        with httpx.Client(timeout=120.0) as client:
            resp = client.post(COZE_STREAM_RUN_URL, headers=headers, json=payload)
            resp.raise_for_status()
            raw_data = resp.text

        # 真实 API 调用成功后才计一次配额
        self._count_call()

        result = _parse_sse_response(raw_data, config["response_format"], platform)
        if result:
            result["source_platform"] = platform
            return result

        return {"success": False, "msg": f"Coze {platform} 工作流返回空结果"}

    def _call_workflow_run(self, workflow_id: str, parameters: dict[str, str]) -> dict[str, Any] | None:
        """调用自定义工作流 (同步 run)"""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "workflow_id": workflow_id,
            "parameters": parameters,
        }

        with httpx.Client(timeout=60.0) as client:
            resp = client.post(COZE_WORKFLOW_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # 真实 API 调用成功后才计一次配额
        self._count_call()

        if data.get("code") != 0:
            msg = data.get("msg", "unknown")
            if resp.status_code == 401 or data.get("code") == 401:
                return {"success": False, "msg": f"Token expired: {msg}"}
            if resp.status_code == 402:
                return {"success": False, "msg": "Insufficient balance (402)"}
            return {"success": False, "msg": f"Coze workflow error: {msg}"}

        execute_data = data.get("data", {})
        if isinstance(execute_data, str):
            try:
                execute_data = json.loads(execute_data)
            except json.JSONDecodeError:
                execute_data = {}
        content = execute_data.get("output", "")
        if not content:
            return {"success": False, "msg": "Coze 工作流返回空内容"}
        return {"success": True, "data": content, "source": "coze_workflow", "source_platform": "coze"}

    @staticmethod
    def _parse_title_from_result(content: str, url: str) -> str:
        text = content.strip()
        if not text:
            return f"Coze 提取结果 ({url})"

        MAX_TITLE = 60
        for delim in ("。", "！", "？", "!", "?", ". "):
            idx = text.find(delim)
            if idx != -1 and 10 < idx < MAX_TITLE:
                return text[:idx + 1].strip()

        for delim in ("，", ", "):
            idx = text.find(delim)
            if idx != -1 and 10 < idx < MAX_TITLE:
                return text[:idx].strip()

        if len(text) > MAX_TITLE:
            return text[:MAX_TITLE].rstrip("，, ") + "…"

        return text


register_extractor("coze", CozeExtractor)
