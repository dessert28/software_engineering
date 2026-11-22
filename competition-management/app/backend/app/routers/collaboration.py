"""路由：团队协作空间与版本复审跟踪（FR-027 / FR-028）。

只依赖共享基座中的模型、枚举与鉴权；Pydantic schema 在本模块内本地定义。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import IssueStatus, RevisionStatus, Role, TeamMemberRole
from app.core.deps import get_current_user, require_roles
from app.db.session import get_session
from app.models import (
    CollaborationNote,
    Competition,
    Enrollment,
    RevisionIssue,
    RevisionReview,
    Submission,
    SubmissionVersion,
    Team,
    TeamMember,
    User,
)

router = APIRouter(tags=["协作与复审"])

# ───────────────────── 本地 schema ─────────────────────
class _ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class NoteCreate(BaseModel):
    content: str = Field(min_length=1)


class NoteOut(_ORMModel):
    id: str
    team_id: str
    author_id: str | None
    content: str
    created_at: datetime
    updated_at: datetime


class RevisionReviewCreate(BaseModel):
    team_id: str
    submission_id: str
    version_id: str
    summary: str | None = None


class RevisionReviewOut(_ORMModel):
    id: str
    competition_id: str
    team_id: str
    submission_id: str
    version_id: str
    status: RevisionStatus
    summary: str | None
    raised_by: str | None
    created_at: datetime
    updated_at: datetime


class RevisionIssueCreate(BaseModel):
    description: str = Field(min_length=2)
    version_id: str | None = None


class RevisionIssueUpdate(BaseModel):
    status: IssueStatus
    resolution_note: str | None = None
    version_id: str | None = None


class RevisionIssueOut(_ORMModel):
    id: str
    review_id: str
    description: str
    version_id: str | None
    status: IssueStatus
    resolution_note: str | None
    handled_by: str | None
    created_at: datetime
    updated_at: datetime


class ReviewDetail(BaseModel):
    review: RevisionReviewOut
    issues: list[RevisionIssueOut]


# ───────────────────── 权限工具 ─────────────────────
# 备注空间对队内所有角色开放（含 ADVISOR）；复审相关操作只面向实际参赛队员。
_REVIEW_TEAM_ROLES = frozenset({TeamMemberRole.CAPTAIN.value, TeamMemberRole.MEMBER.value})
_review_editors = require_roles(Role.CAPTAIN, Role.MEMBER, Role.ADMIN)


def _is_admin(user: User) -> bool:
    return user.role == Role.ADMIN.value


async def _is_member(
    session: AsyncSession, team_id: str, user_id: str, roles: frozenset[str] | None = None
) -> bool:
    stmt = select(TeamMember).where(
        TeamMember.team_id == team_id, TeamMember.user_id == user_id
    )
    if roles is not None:
        stmt = stmt.where(TeamMember.role_in_team.in_(roles))
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _require_access(
    session: AsyncSession,
    team_id: str,
    user: User,
    roles: frozenset[str] | None = None,
    detail: str = "只有该队成员或管理员可以执行此操作",
) -> None:
    if _is_admin(user):
        return
    if not await _is_member(session, team_id, user.id, roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail)


# ───────────────────── FR-027 协作备注 ─────────────────────
@router.post(
    "/teams/{team_id}/notes",
    response_model=NoteOut,
    status_code=status.HTTP_201_CREATED,
    summary="写队内协作备注（FR-027）",
)
async def create_note(
    team_id: str,
    payload: NoteCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> NoteOut:
    team = await session.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "队伍不存在")
    await _require_access(session, team_id, user)

    note = CollaborationNote(
        team_id=team_id, author_id=user.id, content=payload.content
    )
    session.add(note)
    await session.flush()
    return NoteOut.model_validate(note)


@router.get(
    "/teams/{team_id}/notes",
    response_model=list[NoteOut],
    summary="读取队内协作备注（FR-027）",
)
async def list_notes(
    team_id: str,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[NoteOut]:
    team = await session.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "队伍不存在")
    await _require_access(session, team_id, user)

    stmt = (
        select(CollaborationNote)
        .where(CollaborationNote.team_id == team_id)
        .order_by(CollaborationNote.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [NoteOut.model_validate(n) for n in rows]


# ───────────────────── FR-028 版本复审 ─────────────────────
@router.post(
    "/competitions/{competition_id}/revision-reviews",
    response_model=RevisionReviewOut,
    status_code=status.HTTP_201_CREATED,
    summary="发起版本复审（FR-028）",
)
async def create_revision_review(
    competition_id: str,
    payload: RevisionReviewCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(_review_editors),
) -> RevisionReviewOut:
    comp = await session.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "赛事不存在")

    team = await session.get(Team, payload.team_id)
    if team is None or team.competition_id != competition_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "队伍不属于该赛事")

    sub = await session.get(Submission, payload.submission_id)
    enr = await session.get(Enrollment, sub.enrollment_id) if sub is not None else None
    if sub is None or enr is None or enr.team_id != payload.team_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "提交记录不属于该队伍")

    version = await session.get(SubmissionVersion, payload.version_id)
    if version is None or version.submission_id != payload.submission_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "版本不属于该提交")

    await _require_access(session, payload.team_id, user, _REVIEW_TEAM_ROLES)

    review = RevisionReview(
        competition_id=competition_id,
        team_id=payload.team_id,
        submission_id=payload.submission_id,
        version_id=payload.version_id,
        status=RevisionStatus.OPEN.value,
        summary=payload.summary,
        raised_by=user.id,
    )
    session.add(review)
    await session.flush()
    return RevisionReviewOut.model_validate(review)


@router.get(
    "/competitions/{competition_id}/revision-reviews",
    response_model=list[RevisionReviewOut],
    summary="复审列表（FR-028）",
)
async def list_revision_reviews(
    competition_id: str,
    status_filter: RevisionStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[RevisionReviewOut]:
    comp = await session.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "赛事不存在")

    stmt = select(RevisionReview).where(RevisionReview.competition_id == competition_id)
    if status_filter is not None:
        stmt = stmt.where(RevisionReview.status == status_filter.value)

    if not _is_admin(user):
        my_team_ids = (
            await session.execute(
                select(TeamMember.team_id).where(TeamMember.user_id == user.id)
            )
        ).scalars().all()
        stmt = stmt.where(RevisionReview.team_id.in_(my_team_ids))

    stmt = stmt.order_by(RevisionReview.created_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return [RevisionReviewOut.model_validate(r) for r in rows]


@router.post(
    "/revision-reviews/{review_id}/issues",
    response_model=RevisionIssueOut,
    status_code=status.HTTP_201_CREATED,
    summary="登记复审问题项（FR-028）",
)
async def create_revision_issue(
    review_id: str,
    payload: RevisionIssueCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RevisionIssueOut:
    review = await session.get(RevisionReview, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "复审记录不存在")
    await _require_access(session, review.team_id, user, _REVIEW_TEAM_ROLES)

    issue = RevisionIssue(
        review_id=review_id,
        description=payload.description,
        version_id=payload.version_id,
        status=IssueStatus.OPEN.value,
    )
    session.add(issue)
    await session.flush()
    return RevisionIssueOut.model_validate(issue)


@router.patch(
    "/revision-issues/{issue_id}",
    response_model=RevisionIssueOut,
    summary="处理复审问题项（FR-028）",
)
async def update_revision_issue(
    issue_id: str,
    payload: RevisionIssueUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RevisionIssueOut:
    issue = await session.get(RevisionIssue, issue_id)
    if issue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "问题项不存在")
    review = await session.get(RevisionReview, issue.review_id)
    assert review is not None
    await _require_access(session, review.team_id, user, _REVIEW_TEAM_ROLES)

    if payload.status in (IssueStatus.RESOLVED, IssueStatus.REJECTED):
        note = payload.resolution_note
        if not note or len(note.strip()) < 2:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "标记已解决或已驳回时必须填写处理说明（至少 2 个字）"
            )

    issue.status = payload.status.value
    issue.resolution_note = payload.resolution_note
    issue.version_id = payload.version_id
    issue.handled_by = user.id
    await session.flush()
    return RevisionIssueOut.model_validate(issue)


@router.get(
    "/revision-reviews/{review_id}",
    response_model=ReviewDetail,
    summary="复审详情与问题项（FR-028）",
)
async def get_revision_review(
    review_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ReviewDetail:
    review = await session.get(RevisionReview, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "复审记录不存在")
    await _require_access(session, review.team_id, user, _REVIEW_TEAM_ROLES)

    stmt = (
        select(RevisionIssue)
        .where(RevisionIssue.review_id == review_id)
        .order_by(RevisionIssue.created_at.asc())
    )
    issues = (await session.execute(stmt)).scalars().all()
    return ReviewDetail(
        review=RevisionReviewOut.model_validate(review),
        issues=[RevisionIssueOut.model_validate(i) for i in issues],
    )
