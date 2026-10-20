"""Discovery provider 默认注册。"""

from __future__ import annotations

from .base import DiscoveryProvider
from .providers.bilibili import BilibiliDiscoveryProvider


def build_default_providers() -> list[DiscoveryProvider]:
    return [BilibiliDiscoveryProvider()]
