"""审计日志：只追加，不修改，不提供删除接口（FR-024）。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AuditAction
from app.models import AuditLog, User


def _dump(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)


async def record(
    session: AsyncSession,
    *,
    action: AuditAction,
    object_type: str,
    object_id: str | None,
    actor: User | None = None,
    before: Any = None,
    after: Any = None,
    reason: str | None = None,
) -> AuditLog:
    log = AuditLog(
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        action=action.value if isinstance(action, AuditAction) else str(action),
        object_type=object_type,
        object_id=object_id,
        before_json=_dump(before),
        after_json=_dump(after),
        reason=reason,
    )
    session.add(log)
    return log
