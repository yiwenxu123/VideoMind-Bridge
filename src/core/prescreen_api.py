"""预筛能力的单实现（REST / CLI / 旧 MCP 共用）。

2026-11-24：把"跑预筛 + 组装响应"从 MCP 旧实现里抽出来，原因有二：

1. 它此前只存在于 **MCP 工具** 里，REST 没有对应端点——于是 MCP 无法改成
   "薄适配器统一走 :8787"（缺少对应端点就只好在 MCP 里再跑一遍引擎）。
2. 响应结构一旦有两份实现就会漂移（本项目已经吃过"两份实现/两份配置"的亏）。
"""

from __future__ import annotations

from typing import Any


def run_prescreen(runtime: Any, url: str, mode: str = "quick") -> dict[str, Any]:
    """执行预筛并返回统一响应结构。

    Args:
        runtime: ``RouterRuntime`` 实例（提供 ``.router`` 与 ``.extract``）
        url: 视频/笔记链接
        mode: ``quick``（零网络，<2ms）或 ``full``（先取元信息再评分，较慢）
    """
    from . import Prescreener
    from .models import CostTier

    prescreener = Prescreener(runtime.router)

    if mode == "full":
        quick_result = runtime.extract(url, max_cost=CostTier.FREE)
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

    cost_grade = result.effective_cost_grade()
    return {
        "url": result.url,
        "platform": result.platform,
        "grade": result.grade.value,
        "cost_grade": cost_grade.value,
        "score": round(result.score, 1),
        "title": result.title,
        "duration_seconds": result.duration_seconds,
        "reasons": result.reasons,
        "recommended_cost_tier": (
            result.recommended_cost_tier.value if result.recommended_cost_tier else None
        ),
        "skip_reason": result.skip_reason,
        "metadata": result.metadata,
    }
