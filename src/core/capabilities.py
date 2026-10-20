"""能力发现 payload（阶段 3：契约集中化）

API 与 MCP 共用同一份结构，避免两边各自拼字段导致漂移。
探测过程只检查依赖/密钥/路径，不加载模型、不发网络请求。
"""

from __future__ import annotations

from typing import Any

from .models import SCHEMA_VERSION


def capabilities_payload() -> dict[str, Any]:
    from ..services.config_manager import ConfigManager
    from .asr import available_transcribers
    from .router import ContentRouter

    cfg = ConfigManager().get_asr_config()
    return {
        "schema_version": SCHEMA_VERSION,
        "asr": {
            "default_chain": list(cfg.chain),
            "language": cfg.language,
            "max_cost": cfg.max_cost,
            "backends": [caps.to_dict() for caps in available_transcribers()],
        },
        "extractors": ContentRouter().list_extractors(),
        "platforms": ["bilibili", "youtube", "douyin", "xiaohongshu"],
    }
