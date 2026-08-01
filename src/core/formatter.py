"""Hermes 兼容输出格式化

将 ExtractResult 格式化为 Hermes content-value-evaluator 可消费的 JSON。
输出格式对齐 Hermes 的 input 要求。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .models import ExtractResult, PrescreenResult


class HermesFormatter:
    """Hermes 兼容格式化器

    将 VMB 提取结果格式化为 Hermes skill 可直接消费的 JSON 格式。
    """

    @staticmethod
    def format_extract_result(result: ExtractResult) -> dict[str, Any]:
        """格式化为 Hermes 兼容的输出

        Args:
            result: 提取结果

        Returns:
            Hermes 兼容的 JSON 字典

        输出格式:
        {
            "success": bool,
            "platform": "bilibili|youtube|douyin|...",
            "title": "视频标题",
            "content": "完整文本内容",
            "source": "使用的提取器",
            "url": "原始URL",
            "cost_tier": "free|cheap|paid|expensive|premium",
            "duration_seconds": float,
            "language": "zh|en|...",
            "error": "错误信息(仅失败时)",
            "metadata": { ... }
        }
        """
        return result.to_dict()

    @staticmethod
    def format_prescreen_result(result: PrescreenResult) -> dict[str, Any]:
        """格式化预筛结果"""
        return {
            "url": result.url,
            "platform": result.platform,
            "title": result.title,
            "duration_seconds": result.duration_seconds,
            "grade": result.grade.value,
            "score": result.score,
            "reasons": result.reasons,
            "metadata": result.metadata,
        }

    @staticmethod
    def format_extract_result_full(
        result: ExtractResult,
        prescreen: PrescreenResult | None = None,
    ) -> dict[str, Any]:
        """完整的 Hermes 兼容输出 (提取+预筛)"""
        output = result.to_dict()

        # 加入 Hermes 需要的标准字段
        output["source_type"] = "video_content"
        output["extracted_at"] = datetime.now().isoformat()
        output["version"] = "2.0"
        # 内容完整性标记: 供 Agent 判断是否拿到了完整正文 (非仅元信息)
        output["content_complete"] = (
            bool(result.success)
            and bool(result.content and result.content.strip())
            and not result.is_placeholder
        )

        if prescreen:
            output["prescreen"] = HermesFormatter.format_prescreen_result(prescreen)

        return output

    @staticmethod
    def to_json(result: ExtractResult, **kwargs) -> str:
        """序列化为 JSON 字符串"""
        data = HermesFormatter.format_extract_result_full(result)
        data.update(kwargs)
        return json.dumps(data, ensure_ascii=False, indent=2)
