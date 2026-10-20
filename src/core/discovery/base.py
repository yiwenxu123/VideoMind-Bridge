"""Discovery provider 抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import CostTier
from .models import CommentsResult, CreatorFeedResult, DiscoveryError


class DiscoveryProvider(ABC):
    """平台发现能力接口；Phase 1 只包含 creator feed。"""

    platform: str = "unknown"
    source_name: str = "discovery"
    _cost_tier: CostTier = CostTier.CHEAP

    def cost_tier(self) -> CostTier:
        return self._cost_tier

    @abstractmethod
    def supports_creator_url(self, url: str) -> bool:
        """URL 是否为该平台的创作者主页。"""
        ...

    @abstractmethod
    def fetch_creator_feed(self, url: str, limit: int) -> CreatorFeedResult:
        """抓取创作者最新作品；错误以 DiscoveryError 抛出。"""
        ...

    def supports_comments(self, url: str) -> bool:
        _ = url
        return False

    def fetch_comments(
        self,
        url: str,
        *,
        limit: int,
        sort: str,
        include_replies: bool,
        max_replies_per_thread: int,
        include_author: bool,
    ) -> CommentsResult:
        _ = (url, limit, sort, include_replies, max_replies_per_thread, include_author)
        raise DiscoveryError("not_supported", "当前平台不支持评论采集")
