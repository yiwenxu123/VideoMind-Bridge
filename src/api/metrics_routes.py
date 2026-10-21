"""平台请求指标只读端点。"""

from __future__ import annotations

from fastapi import APIRouter

from ..core.models import SCHEMA_VERSION
from ..core.platforms.rate_limit import get_platform_rate_limiter

router = APIRouter(prefix="/api/v1", tags=["metrics"])


@router.get("/metrics", response_model=dict)
def get_metrics() -> dict:
    limiter = get_platform_rate_limiter()
    return {
        "schema_version": SCHEMA_VERSION,
        "enabled": limiter.enabled,
        "platforms": limiter.metrics_snapshot(),
    }
