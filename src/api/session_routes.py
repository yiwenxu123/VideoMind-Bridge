"""平台登录态只读状态与显式检查。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.models import SCHEMA_VERSION
from ..core.platforms.session import (
    SessionCheckUnsupported,
    SessionStatus,
    get_session_manager,
)
from .models import SessionsResponse, SessionStatusResponse

router = APIRouter(prefix="/api/v1", tags=["sessions"])


def _to_response(status: SessionStatus) -> SessionStatusResponse:
    return SessionStatusResponse(
        platform=status.platform,
        configured=status.configured,
        source=status.source,
        cookie_count=status.cookie_count,
        expires_at=status.expires_at,
        valid=status.valid,
        last_checked=status.last_checked,
        error_code=status.error_code,
        warning=status.warning,
    )


@router.get(
    "/sessions",
    response_model=SessionsResponse,
    response_model_exclude_none=True,
)
def list_sessions() -> SessionsResponse:
    statuses = get_session_manager().statuses()
    return SessionsResponse(
        schema_version=SCHEMA_VERSION,
        sessions=[_to_response(status) for status in statuses],
    )


@router.post(
    "/sessions/{platform}/check",
    response_model=SessionStatusResponse,
    response_model_exclude_none=True,
)
def check_session(platform: str) -> SessionStatusResponse:
    try:
        status = get_session_manager().check(platform)
    except SessionCheckUnsupported as exc:
        raise HTTPException(
            status_code=422,
            detail=f"平台不支持会话检查: {platform}",
        ) from exc
    return _to_response(status)
