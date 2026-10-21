"""能力发现 payload（阶段 3：契约集中化）

API 与 MCP 共用同一份结构，避免两边各自拼字段导致漂移。
探测过程只检查依赖/密钥/路径，不加载模型、不发网络请求。
"""

from __future__ import annotations

from typing import Any

from .models import SCHEMA_VERSION


def capabilities_payload(
    extractor_status: dict[str, bool] | None = None,
) -> dict[str, Any]:
    from ..services.config_manager import ConfigManager
    from .asr import available_transcribers

    cfg = ConfigManager().get_asr_config()
    if extractor_status is None:
        from .router import ContentRouter
        extractor_status = ContentRouter().list_extractors()
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "asr": {
            "default_chain": list(cfg.chain),
            "language": cfg.language,
            "max_cost": cfg.max_cost,
            "backends": [caps.to_dict() for caps in available_transcribers()],
        },
        "extractors": extractor_status,
        "platforms": ["bilibili", "youtube", "douyin", "xiaohongshu"],
    }

    from .discovery.config import (
        COMMENTS_PLATFORMS,
        CREATOR_FEED_PLATFORMS,
        DEFAULT_COMMENTS_LIMIT,
        DEFAULT_CREATOR_FEED_LIMIT,
        DEFAULT_REPLIES_PER_THREAD,
        MAX_COMMENTS_LIMIT,
        MAX_CREATOR_FEED_LIMIT,
        MAX_REPLIES_PER_THREAD,
        comments_enabled,
        creator_feed_enabled,
    )

    discovery: dict[str, Any] = {}
    if creator_feed_enabled():
        discovery["creator_feed"] = {
            "enabled": True,
            "platforms": list(CREATOR_FEED_PLATFORMS),
            "limits": {
                "default": DEFAULT_CREATOR_FEED_LIMIT,
                "max": MAX_CREATOR_FEED_LIMIT,
            },
        }
    if comments_enabled():
        discovery["comments"] = {
            "enabled": True,
            "platforms": list(COMMENTS_PLATFORMS),
            "limits": {
                "default": DEFAULT_COMMENTS_LIMIT,
                "max": MAX_COMMENTS_LIMIT,
                "replies_per_thread_default": DEFAULT_REPLIES_PER_THREAD,
                "replies_per_thread_max": MAX_REPLIES_PER_THREAD,
            },
        }
    if discovery:
        payload["discovery"] = discovery
    return payload
