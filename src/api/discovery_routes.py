"""Discovery API 路由（Phase 1：creator feed）。"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, FastAPI, HTTPException

from ..core.discovery.config import comments_enabled, creator_feed_enabled
from ..core.discovery.models import DiscoveryError
from ..core.discovery.service import DiscoveryService
from .models import (
    CommentsRequest,
    CommentsResponse,
    CreatorFeedRequest,
    CreatorFeedResponse,
)

creator_router = APIRouter(prefix="/api/v1", tags=["discovery"])
comments_router = APIRouter(prefix="/api/v1", tags=["discovery"])
_service: DiscoveryService | None = None


def get_discovery_service() -> DiscoveryService:
    global _service
    if _service is None:
        _service = DiscoveryService()
    return _service


@creator_router.post(
    "/creator/feed",
    response_model=CreatorFeedResponse,
    response_model_exclude_none=True,
)
def creator_feed(request: CreatorFeedRequest) -> CreatorFeedResponse:
    try:
        result = get_discovery_service().creator_feed(
            str(request.url),
            limit=request.limit,
            max_cost=request.max_cost,
            request_id=uuid4().hex,
        )
    except DiscoveryError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return CreatorFeedResponse(**result.to_dict())


@comments_router.post(
    "/comments",
    response_model=CommentsResponse,
    response_model_exclude_none=True,
)
def comments(request: CommentsRequest) -> CommentsResponse:
    try:
        result = get_discovery_service().comments(
            str(request.url),
            limit=request.limit,
            sort=request.sort,
            include_replies=request.include_replies,
            max_replies_per_thread=request.max_replies_per_thread,
            include_author=request.include_author,
            max_cost=request.max_cost,
            request_id=uuid4().hex,
        )
    except DiscoveryError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return CommentsResponse(**result.to_dict())


def include_discovery_routes(app: FastAPI) -> None:
    if creator_feed_enabled():
        app.include_router(creator_router)
    if comments_enabled():
        app.include_router(comments_router)
