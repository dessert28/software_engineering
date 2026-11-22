"""路由：站内通知中心（FR-005）。

一对一（recipient_id）或按角色广播（target_role），记录已读状态并写审计。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AuditAction, NotificationStatus, Role
from app.core.deps import get_current_user, require_roles
from app.db.session import get_session
from app.models import Notification, User
from app.services import audit

router = APIRouter(prefix="/notifications", tags=["通知"])

_admin = require_roles(Role.ADMIN)


# ───────────────────── 本地 schema（不污染 schemas/__init__.py）─────────────────────
class NotificationCreate(BaseModel):
    competition_id: str | None = None
    recipient_id: str | None = None
    target_role: str | None = None
    title: str = Field(min_length=2, max_length=200)
    body: str = ""
    channel: str = "IN_APP"


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    competition_id: str | None
    recipient_id: str | None
    target_role: str | None
    title: str
    body: str
    status: str
    channel: str
    read_by: str | None
    read_at: datetime | None
    created_at: datetime


class UnreadCount(BaseModel):
    count: int


def _visible_to(notification: Notification, user: User) -> bool:
    """通知是否发给当前用户：指定收件人或按角色广播命中。"""
    return notification.recipient_id == user.id or notification.target_role == user.role


def _mine_stmt(user: User):
    return select(Notification).where(
        or_(
            Notification.recipient_id == user.id,
            Notification.target_role == user.role,
        )
    )


# ───────────────────── 发送 ─────────────────────
@router.post("", response_model=list[NotificationOut], status_code=201, summary="发送通知（FR-005）")
async def create_notification(
    payload: NotificationCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> list[NotificationOut]:
    recipient_id = payload.recipient_id
    target_role = payload.target_role
    if not recipient_id and not target_role:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "recipient_id 与 target_role 至少提供一个"
        )

    # 指定收件人优先：校验用户存在，只发给这一个人。
    if recipient_id:
        user = await session.get(User, recipient_id)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "收件用户不存在")
        recipient_ids = [user.id]
        target_role = None
    else:
        # 按角色广播给所有处于激活状态的用户。
        recipient_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.role == target_role,
                        User.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )

    created: list[Notification] = []
    for rid in recipient_ids:
        note = Notification(
            competition_id=payload.competition_id,
            recipient_id=recipient_id,
            target_role=target_role,
            title=payload.title,
            body=payload.body,
            channel=payload.channel,
            status=NotificationStatus.SENT.value,
        )
        session.add(note)
        created.append(note)
    await session.flush()

    await audit.record(
        session,
        action=AuditAction.NOTIFY,
        object_type="Notification",
        object_id=created[0].id if created else None,
        actor=admin,
        after={
            "count": len(created),
            "recipient_id": recipient_id,
            "target_role": target_role,
            "title": payload.title,
        },
    )
    await session.flush()
    return [NotificationOut.model_validate(n) for n in created]


# ───────────────────── 收件箱 ─────────────────────
# 注意：/mine、/mine/unread-count 必须定义在 /{notification_id}/read 之前，
# 避免被动态路径提前匹配。
@router.get("/mine", response_model=list[NotificationOut], summary="我的通知（FR-005）")
async def list_mine(
    unread_only: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[NotificationOut]:
    stmt = _mine_stmt(user)
    if unread_only:
        stmt = stmt.where(Notification.status != NotificationStatus.READ.value)
    rows = (await session.execute(stmt.order_by(Notification.created_at.desc()))).scalars().all()
    return [NotificationOut.model_validate(n) for n in rows]


@router.get("/mine/unread-count", response_model=UnreadCount, summary="未读数量（FR-005）")
async def unread_count(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> UnreadCount:
    stmt = select(func.count(Notification.id)).where(
        or_(
            Notification.recipient_id == user.id,
            Notification.target_role == user.role,
        ),
        Notification.status != NotificationStatus.READ.value,
    )
    count = (await session.execute(stmt)).scalar_one()
    return UnreadCount(count=count)


@router.post("/{notification_id}/read", response_model=NotificationOut, summary="标记已读（FR-005）")
async def mark_read(
    notification_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> NotificationOut:
    note = await session.get(Notification, notification_id)
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "通知不存在")
    if not _visible_to(note, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权标记此通知")
    if note.status == NotificationStatus.READ.value:
        return NotificationOut.model_validate(note)

    note.status = NotificationStatus.READ.value
    note.read_by = user.id
    note.read_at = datetime.now(UTC)
    await session.flush()
    return NotificationOut.model_validate(note)


# ───────────────────── 管理视图 ─────────────────────
@router.get("", response_model=list[NotificationOut], summary="全部通知（FR-005）")
async def list_all(
    competition_id: str | None = Query(default=None),
    role: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(_admin),
) -> list[NotificationOut]:
    stmt = select(Notification).order_by(Notification.created_at.desc())
    if competition_id:
        stmt = stmt.where(Notification.competition_id == competition_id)
    if role:
        stmt = stmt.where(Notification.target_role == role)
    rows = (await session.execute(stmt)).scalars().all()
    return [NotificationOut.model_validate(n) for n in rows]
