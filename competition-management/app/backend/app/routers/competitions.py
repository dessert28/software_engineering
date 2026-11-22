"""路由：赛事（FR-001～FR-004）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AuditAction, CompetitionState, Role
from app.core.deps import get_current_user, require_roles
from app.db.session import get_session
from app.models import Announcement, Competition, ProblemSet, User
from app.schemas import (
    AnnouncementCreate,
    AnnouncementOut,
    CompetitionCreate,
    CompetitionOut,
    CompetitionUpdate,
    ProblemCreate,
    ProblemOut,
    TransitionOut,
    TransitionRequest,
)
from app.services import audit
from app.services.rules import allowed_next_states, validate_transition

router = APIRouter(prefix="/competitions", tags=["赛事"])

_admin = require_roles(Role.ADMIN)


async def _get_competition(session: AsyncSession, competition_id: str) -> Competition:
    comp = await session.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "赛事不存在")
    return comp


# ───────────────────── 赛事 CRUD ─────────────────────
@router.get("", response_model=list[CompetitionOut], summary="赛事列表")
async def list_competitions(
    state: CompetitionState | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> list[CompetitionOut]:
    stmt = select(Competition).order_by(Competition.created_at.desc())
    if state is not None:
        stmt = stmt.where(Competition.state == state.value)
    rows = (await session.execute(stmt)).scalars().all()
    return [CompetitionOut.model_validate(c) for c in rows]


@router.post("", response_model=CompetitionOut, status_code=201, summary="创建赛事（草稿）")
async def create_competition(
    payload: CompetitionCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> CompetitionOut:
    comp = Competition(
        **payload.model_dump(exclude={"registration_opens_at"}),
        registration_opens_at=payload.registration_opens_at,
        state=CompetitionState.DRAFT.value,
        created_by=admin.id,
    )
    session.add(comp)
    await session.flush()
    await audit.record(
        session,
        action=AuditAction.CREATE,
        object_type="Competition",
        object_id=comp.id,
        actor=admin,
        after={"title": comp.title, "state": comp.state},
    )
    return CompetitionOut.model_validate(comp)


@router.get("/{competition_id}", response_model=CompetitionOut, summary="赛事详情")
async def get_competition(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> CompetitionOut:
    return CompetitionOut.model_validate(await _get_competition(session, competition_id))


@router.patch("/{competition_id}", response_model=CompetitionOut, summary="编辑赛事")
async def update_competition(
    competition_id: str,
    payload: CompetitionUpdate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> CompetitionOut:
    comp = await _get_competition(session, competition_id)
    if comp.state == CompetitionState.ARCHIVED.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "已归档赛事不可编辑")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return CompetitionOut.model_validate(comp)

    before = {k: getattr(comp, k) for k in changes}
    for k, v in changes.items():
        setattr(comp, k, v)

    await audit.record(
        session,
        action=AuditAction.UPDATE,
        object_type="Competition",
        object_id=comp.id,
        actor=admin,
        before=before,
        after=changes,
    )
    await session.flush()
    return CompetitionOut.model_validate(comp)


# ───────────────────── 生命周期 ─────────────────────
@router.post("/{competition_id}/transition", response_model=TransitionOut, summary="状态迁移（FR-002）")
async def transition(
    competition_id: str,
    payload: TransitionRequest,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> TransitionOut:
    comp = await _get_competition(session, competition_id)
    current = CompetitionState(comp.state)

    validate_transition(current, payload.target, payload.reason)

    comp.state = payload.target.value
    await audit.record(
        session,
        action=AuditAction.TRANSITION,
        object_type="Competition",
        object_id=comp.id,
        actor=admin,
        before={"state": current.value},
        after={"state": payload.target.value},
        reason=payload.reason,
    )
    await session.flush()
    return TransitionOut(
        competition=CompetitionOut.model_validate(comp),
        previous_state=current,
        allowed_next=allowed_next_states(payload.target),
    )


# ───────────────────── 公告（FR-004）─────────────────────
@router.post(
    "/{competition_id}/announcements",
    response_model=AnnouncementOut,
    status_code=201,
    summary="发布公告",
)
async def create_announcement(
    competition_id: str,
    payload: AnnouncementCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> AnnouncementOut:
    await _get_competition(session, competition_id)
    ann = Announcement(competition_id=competition_id, published_by=admin.id, **payload.model_dump())
    session.add(ann)
    await session.flush()
    await audit.record(
        session,
        action=AuditAction.CREATE,
        object_type="Announcement",
        object_id=ann.id,
        actor=admin,
        after={"title": ann.title},
    )
    return AnnouncementOut.model_validate(ann)


@router.get(
    "/{competition_id}/announcements",
    response_model=list[AnnouncementOut],
    summary="公告列表",
)
async def list_announcements(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> list[AnnouncementOut]:
    stmt = (
        select(Announcement)
        .where(Announcement.competition_id == competition_id, Announcement.is_withdrawn.is_(False))
        .order_by(Announcement.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [AnnouncementOut.model_validate(a) for a in rows]


# ───────────────────── 题目 ─────────────────────
@router.post(
    "/{competition_id}/problems",
    response_model=ProblemOut,
    status_code=201,
    summary="新增题目",
)
async def create_problem(
    competition_id: str,
    payload: ProblemCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> ProblemOut:
    await _get_competition(session, competition_id)
    exists = (
        await session.execute(
            select(ProblemSet).where(
                ProblemSet.competition_id == competition_id, ProblemSet.code == payload.code
            )
        )
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, f"题目编号 {payload.code} 已存在")

    prob = ProblemSet(competition_id=competition_id, **payload.model_dump())
    session.add(prob)
    await session.flush()
    return ProblemOut.model_validate(prob)


@router.get("/{competition_id}/problems", response_model=list[ProblemOut], summary="题目列表")
async def list_problems(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[ProblemOut]:
    stmt = select(ProblemSet).where(ProblemSet.competition_id == competition_id)
    if user.role != Role.ADMIN.value:
        stmt = stmt.where(ProblemSet.is_published.is_(True))
    rows = (await session.execute(stmt.order_by(ProblemSet.code))).scalars().all()
    return [ProblemOut.model_validate(p) for p in rows]
