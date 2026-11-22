"""路由：审计日志（FR-024）。只读，无删除接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import Role
from app.core.deps import require_roles
from app.db.session import get_session
from app.models import AuditLog, User
from app.schemas import AuditOut

router = APIRouter(prefix="/audit", tags=["审计"])

_admin = require_roles(Role.ADMIN)


@router.get("", response_model=list[AuditOut], summary="审计日志（FR-024）")
async def list_logs(
    object_type: str | None = Query(default=None),
    object_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(_admin),
) -> list[AuditOut]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if object_type:
        stmt = stmt.where(AuditLog.object_type == object_type)
    if object_id:
        stmt = stmt.where(AuditLog.object_id == object_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)

    rows = (await session.execute(stmt)).scalars().all()
    return [AuditOut.model_validate(r) for r in rows]
