"""路由：队伍与报名（FR-006～FR-008）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import (
    AuditAction,
    CompetitionState,
    EnrollmentStatus,
    Role,
    TeamMemberRole,
)
from app.core.deps import get_current_user, require_roles
from app.core.security import hash_password
from app.db.session import get_session
from app.models import Competition, Enrollment, Team, TeamMember, User
from app.schemas import (
    EnrollmentCreate,
    EnrollmentOut,
    EnrollmentReview,
    TeamCreate,
    TeamMemberAdd,
    TeamOut,
)
from app.services import audit

router = APIRouter(tags=["队伍与报名"])

_admin = require_roles(Role.ADMIN)


async def _load_team(session: AsyncSession, team_id: str) -> Team:
    stmt = (
        select(Team)
        .where(Team.id == team_id)
        .options(selectinload(Team.members).selectinload(TeamMember.user))
    )
    team = (await session.execute(stmt)).scalar_one_or_none()
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "队伍不存在")
    return team


# ───────────────────── 队伍 ─────────────────────
@router.post("/teams", response_model=TeamOut, status_code=201, summary="创建队伍（FR-006）")
async def create_team(
    payload: TeamCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TeamOut:
    comp = await session.get(Competition, payload.competition_id)
    if comp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "赛事不存在")
    # 只有报名开放期能建队
    if comp.state != CompetitionState.REGISTRATION_OPEN.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "当前不在报名开放期")

    team = Team(**payload.model_dump())
    session.add(team)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "该赛事下已有同名队伍") from None

    # 创建者自动成为队长
    session.add(
        TeamMember(team_id=team.id, user_id=user.id, role_in_team=TeamMemberRole.CAPTAIN.value)
    )
    await audit.record(
        session,
        action=AuditAction.CREATE,
        object_type="Team",
        object_id=team.id,
        actor=user,
        after={"name": team.name, "competition_id": team.competition_id},
    )
    await session.flush()
    return TeamOut.model_validate(await _load_team(session, team.id))


@router.get("/teams/{team_id}", response_model=TeamOut, summary="队伍详情")
async def get_team(
    team_id: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> TeamOut:
    return TeamOut.model_validate(await _load_team(session, team_id))


@router.get("/teams", response_model=list[TeamOut], summary="我所在的队伍")
async def list_my_teams(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[TeamOut]:
    stmt = (
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user.id)
        .options(selectinload(Team.members))
    )
    rows = (await session.execute(stmt)).scalars().unique().all()
    return [TeamOut.model_validate(t) for t in rows]


@router.post("/teams/{team_id}/members", response_model=TeamOut, summary="添加成员（FR-007）")
async def add_member(
    team_id: str,
    payload: TeamMemberAdd,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TeamOut:
    team = await _load_team(session, team_id)
    comp = await session.get(Competition, team.competition_id)
    assert comp is not None

    # 只有队长和管理员能加人
    is_captain = any(m.user_id == user.id and m.role_in_team == TeamMemberRole.CAPTAIN.value for m in team.members)
    if not is_captain and user.role != Role.ADMIN.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只有队长或管理员可以添加成员")

    if payload.role_in_team != TeamMemberRole.ADVISOR:
        current = sum(1 for m in team.members if m.role_in_team != TeamMemberRole.ADVISOR.value)
        if current >= comp.max_team_size:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"队伍人数已达上限 {comp.max_team_size} 人"
            )

    # 按 user_id 或 email 定位用户；两者都没有则新建一个 MEMBER 账号
    target: User | None = None
    if payload.user_id:
        target = await session.get(User, payload.user_id)
    elif payload.email:
        target = (
            await session.execute(select(User).where(User.email == payload.email))
        ).scalar_one_or_none()
        if target is None:
            if not payload.name:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "新建成员时必须提供 name")
            target = User(
                email=payload.email,
                name=payload.name,
                role=Role.MEMBER.value,
                password_hash=hash_password("Passw0rd!"),
            )
            session.add(target)
            await session.flush()
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "必须提供 user_id 或 email")

    dup = (
        await session.execute(
            select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == target.id)
        )
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, "该用户已在队伍中")

    session.add(
        TeamMember(
            team_id=team_id,
            user_id=target.id,
            role_in_team=payload.role_in_team.value,
            contact=payload.contact,
        )
    )
    await session.flush()
    return TeamOut.model_validate(await _load_team(session, team_id))


# ───────────────────── 报名 ─────────────────────
@router.post("/enrollments", response_model=EnrollmentOut, status_code=201, summary="提交报名")
async def create_enrollment(
    payload: EnrollmentCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> EnrollmentOut:
    comp = await session.get(Competition, payload.competition_id)
    if comp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "赛事不存在")
    if comp.state != CompetitionState.REGISTRATION_OPEN.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "当前不在报名开放期")

    team = await _load_team(session, payload.team_id)
    if team.competition_id != payload.competition_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "队伍不属于该赛事")

    member_count = sum(1 for m in team.members if m.role_in_team != TeamMemberRole.ADVISOR.value)
    if member_count < comp.min_team_size:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"队伍人数不足，至少需要 {comp.min_team_size} 人"
        )

    enr = Enrollment(
        competition_id=payload.competition_id,
        team_id=payload.team_id,
        status=EnrollmentStatus.PENDING.value,
    )
    session.add(enr)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "该队伍已报名此赛事") from None

    await audit.record(
        session,
        action=AuditAction.CREATE,
        object_type="Enrollment",
        object_id=enr.id,
        actor=user,
        after={"team_id": team.id, "competition_id": payload.competition_id},
    )
    return EnrollmentOut.model_validate(enr)


@router.get("/enrollments", response_model=list[EnrollmentOut], summary="报名列表")
async def list_enrollments(
    competition_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[EnrollmentOut]:
    stmt = select(Enrollment).order_by(Enrollment.created_at.desc())
    if competition_id:
        stmt = stmt.where(Enrollment.competition_id == competition_id)

    if user.role != Role.ADMIN.value:
        # 非管理员只看自己队伍
        stmt = stmt.join(TeamMember, TeamMember.team_id == Enrollment.team_id).where(
            TeamMember.user_id == user.id
        )

    rows = (await session.execute(stmt)).scalars().unique().all()
    return [EnrollmentOut.model_validate(e) for e in rows]


@router.post(
    "/enrollments/{enrollment_id}/review",
    response_model=EnrollmentOut,
    summary="审核报名资格（FR-008）",
)
async def review_enrollment(
    enrollment_id: str,
    payload: EnrollmentReview,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> EnrollmentOut:
    enr = await session.get(Enrollment, enrollment_id)
    if enr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "报名记录不存在")

    before = {"status": enr.status}
    enr.status = payload.status.value
    enr.review_comment = payload.comment
    enr.reviewed_by = admin.id
    enr.reviewed_at = func.now()

    await audit.record(
        session,
        action=AuditAction.UPDATE,
        object_type="Enrollment",
        object_id=enr.id,
        actor=admin,
        before=before,
        after={"status": enr.status, "comment": payload.comment},
    )
    await session.flush()
    return EnrollmentOut.model_validate(enr)
