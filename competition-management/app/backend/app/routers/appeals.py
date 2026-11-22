"""路由：成绩申诉的提交与处理（FR-022、FR-023）。

参赛方（队长/指导教师）在成绩发布或申诉期提交申诉，管理员指派并处理。
本模块只负责申诉状态与处理意见的留痕，不修改 CompetitionResult（成绩调整属后续版本）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    AppealStatus,
    AuditAction,
    CompetitionState,
    Role,
    TeamMemberRole,
)
from app.core.deps import get_current_user, require_roles
from app.db.session import get_session
from app.models import Appeal, Competition, Team, TeamMember, User
from app.services import audit

router = APIRouter(tags=["申诉"])

_admin = require_roles(Role.ADMIN)
_submitter = require_roles(Role.CAPTAIN, Role.TEACHER)


# ───────────────────── 本地 schema（不污染 schemas/__init__.py）─────────────────────
class AppealCreate(BaseModel):
    competition_id: str
    team_id: str
    reason: str = Field(min_length=10)


class AssignBody(BaseModel):
    handler_id: str


class DecisionBody(BaseModel):
    decision: Literal["ACCEPTED", "REJECTED", "WITHDRAWN"]
    resolution: str = Field(min_length=5)


class AppealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    appeal_no: str
    competition_id: str
    team_id: str
    submitted_by: str | None
    reason: str
    status: str
    resolution: str | None
    decision: str | None
    handled_by: str | None
    handled_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ───────────────────── 辅助 ─────────────────────
async def _my_team_ids(session: AsyncSession, user_id: str) -> set[str]:
    """当前用户作为成员（任意队内角色）所在的队伍集合。"""
    rows = (
        await session.execute(select(TeamMember).where(TeamMember.user_id == user_id))
    ).scalars().all()
    return {m.team_id for m in rows}


# ───────────────────── 提交与查询 ─────────────────────
@router.post("/appeals", response_model=AppealOut, summary="提交成绩申诉（FR-022）")
async def submit_appeal(
    payload: AppealCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(_submitter),
) -> AppealOut:
    comp = await session.get(Competition, payload.competition_id)
    if comp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "赛事不存在")
    if comp.state not in (CompetitionState.RESULT_PUBLISHED.value, CompetitionState.APPEAL.value):
        raise HTTPException(status.HTTP_409_CONFLICT, "当前不在申诉受理期")

    team = await session.get(Team, payload.team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "队伍不存在")
    if team.competition_id != payload.competition_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "队伍不属于该赛事")

    # 队长必须是该队 CAPTAIN；教师必须是该队 ADVISOR
    expected_role = (
        TeamMemberRole.CAPTAIN if user.role == Role.CAPTAIN.value else TeamMemberRole.ADVISOR
    )
    membership = (
        await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == payload.team_id,
                TeamMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if membership is None or membership.role_in_team != expected_role.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权为该队伍提交申诉")

    # 同一队伍+赛事已有处理中的申诉则拒绝重复提交
    existing = (
        await session.execute(
            select(Appeal).where(
                Appeal.competition_id == payload.competition_id,
                Appeal.team_id == payload.team_id,
                Appeal.status.in_([AppealStatus.OPEN.value, AppealStatus.ASSIGNED.value]),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "该队伍已有处理中的申诉")

    appeal = Appeal(
        competition_id=payload.competition_id,
        team_id=payload.team_id,
        submitted_by=user.id,
        reason=payload.reason,
        status=AppealStatus.OPEN.value,
    )
    session.add(appeal)
    await session.flush()

    await audit.record(
        session,
        action=AuditAction.APPEAL,
        object_type="Appeal",
        object_id=appeal.id,
        actor=user,
        after={"status": appeal.status, "team_id": appeal.team_id},
    )
    await session.flush()
    return AppealOut.model_validate(appeal)


@router.get("/appeals/mine", response_model=list[AppealOut], summary="我的申诉（FR-022）")
async def list_my_appeals(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[AppealOut]:
    team_ids = await _my_team_ids(session, user.id)
    stmt = select(Appeal).where(
        or_(Appeal.submitted_by == user.id, Appeal.team_id.in_(team_ids))
    )
    rows = (await session.execute(stmt.order_by(Appeal.created_at.desc()))).scalars().all()
    return [AppealOut.model_validate(a) for a in rows]


@router.get(
    "/competitions/{competition_id}/appeals",
    response_model=list[AppealOut],
    summary="赛事申诉列表（管理员，FR-023）",
)
async def list_competition_appeals(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(_admin),
) -> list[AppealOut]:
    rows = (
        await session.execute(
            select(Appeal)
            .where(Appeal.competition_id == competition_id)
            .order_by(Appeal.created_at.desc())
        )
    ).scalars().all()
    return [AppealOut.model_validate(a) for a in rows]


# ───────────────────── 处理 ─────────────────────
@router.post(
    "/appeals/{appeal_id}/assign",
    response_model=AppealOut,
    summary="指派申诉处理人（FR-023）",
)
async def assign_appeal(
    appeal_id: str,
    payload: AssignBody,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> AppealOut:
    appeal = await session.get(Appeal, appeal_id)
    if appeal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "申诉不存在")
    if appeal.status != AppealStatus.OPEN.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "只有 OPEN 状态的申诉可以指派")

    handler = await session.get(User, payload.handler_id)
    if handler is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "处理人不存在")

    before = {"status": appeal.status, "handled_by": appeal.handled_by}
    appeal.status = AppealStatus.ASSIGNED.value
    appeal.handled_by = payload.handler_id

    await audit.record(
        session,
        action=AuditAction.APPEAL,
        object_type="Appeal",
        object_id=appeal.id,
        actor=admin,
        before=before,
        after={"status": appeal.status, "handled_by": appeal.handled_by},
    )
    await session.flush()
    return AppealOut.model_validate(appeal)


@router.post(
    "/appeals/{appeal_id}/decide",
    response_model=AppealOut,
    summary="裁决申诉（FR-023）",
)
async def decide_appeal(
    appeal_id: str,
    payload: DecisionBody,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AppealOut:
    appeal = await session.get(Appeal, appeal_id)
    if appeal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "申诉不存在")
    if appeal.status not in (
        AppealStatus.OPEN.value,
        AppealStatus.ASSIGNED.value,
        AppealStatus.ACCEPTED.value,
        AppealStatus.REJECTED.value,
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "当前申诉状态不可裁决")
    if user.role != Role.ADMIN.value and appeal.handled_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只有管理员或指定处理人可以裁决")

    before = {
        "status": appeal.status,
        "decision": appeal.decision,
        "resolution": appeal.resolution,
    }
    appeal.status = payload.decision
    appeal.decision = payload.decision
    appeal.resolution = payload.resolution
    if not appeal.handled_by:
        appeal.handled_by = user.id
    appeal.handled_at = datetime.now(UTC)

    await audit.record(
        session,
        action=AuditAction.APPEAL,
        object_type="Appeal",
        object_id=appeal.id,
        actor=user,
        before=before,
        after={
            "status": appeal.status,
            "decision": appeal.decision,
            "resolution": appeal.resolution,
        },
    )
    await session.flush()
    return AppealOut.model_validate(appeal)


# 注意：/appeals/mine 必须在 /appeals/{appeal_id} 之前声明，避免被当作 appeal_id 匹配。
@router.get("/appeals/{appeal_id}", response_model=AppealOut, summary="申诉详情（FR-022）")
async def get_appeal(
    appeal_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AppealOut:
    appeal = await session.get(Appeal, appeal_id)
    if appeal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "申诉不存在")

    # 管理员/评审/教师宽松可读；其余仅提交人或本队成员可读
    if user.role not in (Role.ADMIN.value, Role.JUDGE.value, Role.TEACHER.value):
        allowed = user.id == appeal.submitted_by
        if not allowed:
            membership = (
                await session.execute(
                    select(TeamMember).where(
                        TeamMember.team_id == appeal.team_id,
                        TeamMember.user_id == user.id,
                    )
                )
            ).scalar_one_or_none()
            allowed = membership is not None
        if not allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "无权查看该申诉")

    return AppealOut.model_validate(appeal)
