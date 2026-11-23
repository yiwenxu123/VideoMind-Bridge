"""平台请求指标只读端点。"""

from __future__ import annotations

from fastapi import APIRouter

from ..core.metrics import get_extraction_metrics
from ..core.models import SCHEMA_VERSION
from ..core.platforms.rate_limit import get_platform_rate_limiter

router = APIRouter(prefix="/api/v1", tags=["metrics"])


@router.get("/metrics", response_model=dict)
def get_metrics() -> dict:
    limiter = get_platform_rate_limiter()
    return {
        "schema_version": SCHEMA_VERSION,
        "enabled": limiter.enabled,
        # platforms: 按平台聚合的请求指标（计数/延迟/成功率）
        "platforms": limiter.metrics_snapshot(),
        # circuits: 按熔断作用域展开的真实状态，如 douyin:crawl / douyin:ytdlp。
        # 2026-11-20 起熔断键不再等于平台名，只看 platforms[*].circuit 会漏掉作用域熔断。
        "circuits": limiter.circuits_snapshot(),
        # extraction: 提取链路命中分布。
        # 回答"这条平台靠字幕还是靠转写""失败主要卡在哪一环""哪条链路其实没被用到"。
        "extraction": get_extraction_metrics().snapshot(),
    }
