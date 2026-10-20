"""Discovery 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import SCHEMA_VERSION, CostTier


class DiscoveryError(RuntimeError):
    """可映射为 API error_code 的采集错误。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class CreatorRef:
    id: str
    name: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "url": self.url}


@dataclass
class CreatorFeedItem:
    id: str
    url: str
    title: str
    published_at: str | None = None
    duration_seconds: float = 0.0
    metrics: dict[str, int] = field(default_factory=dict)
    cover_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "duration_seconds": self.duration_seconds,
        }
        if self.published_at:
            payload["published_at"] = self.published_at
        if self.metrics:
            payload["metrics"] = dict(self.metrics)
        if self.cover_url:
            payload["cover_url"] = self.cover_url
        return payload


@dataclass
class CommentItem:
    id: str
    parent_id: str | None
    root_id: str
    text: str
    likes: int = 0
    created_at: str | None = None
    is_reply: bool = False
    reply_count: int = 0
    author_display_name: str | None = None
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "parent_id": self.parent_id,
            "root_id": self.root_id,
            "text": self.text,
            "likes": self.likes,
            "is_reply": self.is_reply,
        }
        if self.created_at:
            payload["created_at"] = self.created_at
        if self.reply_count:
            payload["reply_count"] = self.reply_count
        if self.author_display_name:
            payload["author"] = {"display_name": self.author_display_name}
        if self.truncated:
            payload["truncated"] = True
        return payload


@dataclass
class CommentsResult:
    success: bool
    platform: str
    source: str
    cost_tier: CostTier
    items: list[CommentItem] = field(default_factory=list)
    completeness: str = "none"
    sampled: bool = True
    cached: bool = False
    fetched_at: str = ""
    sort: str = "hot"
    has_more: bool = False
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    error_code: str | None = None
    retry_after_seconds: int | None = None
    request_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        top_level_count = sum(1 for item in self.items if not item.is_reply)
        reply_count = len(self.items) - top_level_count
        payload: dict[str, Any] = {
            "success": self.success,
            "schema_version": SCHEMA_VERSION,
            "request_id": self.request_id,
            "platform": self.platform,
            "source": self.source,
            "cost_tier": self.cost_tier.value,
            "completeness": self.completeness,
            "sampled": self.sampled,
            "cached": self.cached,
            "fetched_at": self.fetched_at,
            "sort": self.sort,
            "items": [item.to_dict() for item in self.items],
            "returned_count": len(self.items),
            "top_level_count": top_level_count,
            "reply_count": reply_count,
            "has_more": self.has_more,
            "warnings": list(self.warnings),
        }
        if self.error:
            payload["error"] = self.error
        if self.error_code:
            payload["error_code"] = self.error_code
        if self.retry_after_seconds is not None:
            payload["retry_after_seconds"] = self.retry_after_seconds
        return payload


@dataclass
class CreatorFeedResult:
    success: bool
    platform: str
    source: str
    cost_tier: CostTier
    creator: CreatorRef | None = None
    items: list[CreatorFeedItem] = field(default_factory=list)
    completeness: str = "none"
    sampled: bool = True
    cached: bool = False
    fetched_at: str = ""
    has_more: bool = False
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    error_code: str | None = None
    retry_after_seconds: int | None = None
    request_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "success": self.success,
            "schema_version": SCHEMA_VERSION,
            "request_id": self.request_id,
            "platform": self.platform,
            "source": self.source,
            "cost_tier": self.cost_tier.value,
            "completeness": self.completeness,
            "sampled": self.sampled,
            "cached": self.cached,
            "fetched_at": self.fetched_at,
            "items": [item.to_dict() for item in self.items],
            "returned_count": len(self.items),
            "has_more": self.has_more,
            "warnings": list(self.warnings),
        }
        if self.creator is not None:
            payload["creator"] = self.creator.to_dict()
        if self.error:
            payload["error"] = self.error
        if self.error_code:
            payload["error_code"] = self.error_code
        if self.retry_after_seconds is not None:
            payload["retry_after_seconds"] = self.retry_after_seconds
        return payload
