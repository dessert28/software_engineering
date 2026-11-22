"""路由：成绩汇总与结果发布（FR-019～FR-021）。"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import (
    AuditAction,
    CompetitionState,
    ResultStatus,
    ReviewTaskStatus,
    Role,
)
from app.core.deps import get_current_user, require_roles
from app.db.session import get_session
from app.models import (
    Competition,
    CompetitionResult,
    Enrollment,
    ReviewTask,
    ScoreRecord,
    Submission,
    Team,
    TeamMember,
    User,
)
from app.schemas import CalculateResponse, ResultOut
from app.services import audit
from app.services.rules import aggregate_scores, assign_ranks

router = APIRouter(tags=["结果"])

_admin = require_roles(Role.ADMIN)


def _award_for(rank: int | None, total: int) -> str | None:
    """按名次比例划奖项：前 10% 一等奖，10%-25% 二等奖，25%-45% 三等奖。"""
    if rank is None or total == 0:
        return None
    ratio = rank / total
    if ratio <= 0.10:
        return "一等奖"
    if ratio <= 0.25:
        return "二等奖"
    if ratio <= 0.45:
        return "三等奖"
    return "成功参赛奖"


@router.post(
    "/competitions/{competition_id}/results/calculate",
    response_model=CalculateResponse,
    summary="汇总成绩与排名（FR-019）",
)
async def calculate_results(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> CalculateResponse:
    comp = await session.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "赛事不存在")
    if comp.state not in (CompetitionState.REVIEWING.value, CompetitionState.RESULT_PENDING.value):
        raise HTTPException(status.HTTP_409_CONFLICT, "只有评审中或结果待发布状态可以汇总")

    # 收集每个提交的评分
    tasks = (
        await session.execute(
            select(ReviewTask)
            .where(ReviewTask.competition_id == competition_id)
            .options(selectinload(ReviewTask.scores))
        )
    ).scalars().unique().all()

    by_submission: dict[str, list[ScoreRecord]] = {}
    for t in tasks:
        if t.status != ReviewTaskStatus.SUBMITTED.value:
            continue
        if t.scores:
            by_submission.setdefault(t.submission_id, []).extend(t.scores)

    strategy = comp.rule_profile.aggregation if comp.rule_profile else "MEAN"

    # 取所有通过审核的报名，未评分的标记为 skipped
    enrollments = (
        await session.execute(
            select(Enrollment).where(
                Enrollment.competition_id == competition_id,
                Enrollment.status == "APPROVED",
            )
        )
    ).scalars().all()

    scored: list[tuple[str, str, float, int]] = []  # team_id, team_name, score, review_count
    skipped: list[str] = []

    for enr in enrollments:
        submission = (
            await session.execute(select(Submission).where(Submission.enrollment_id == enr.id))
        ).scalar_one_or_none()
        if submission is None:
            skipped.append(f"队伍 {enr.team_id}：未创建提交")
            continue

        scores = by_submission.get(submission.id, [])
        if not scores:
            skipped.append(f"队伍 {enr.team_id}：尚无有效评分")
            continue

        team = await session.get(Team, enr.team_id)
        final = aggregate_scores(scores, strategy)
        scored.append((enr.team_id, team.name if team else enr.team_id, final, len(scores)))

    # 排名
    rank_map = assign_ranks([(t[0], t[2]) for t in scored])
    total_teams = len(scored)

    results: list[CompetitionResult] = []
    for team_id, team_name, final, count in scored:
        rank = rank_map.get(team_id)
        row = (
            await session.execute(
                select(CompetitionResult).where(
                    CompetitionResult.competition_id == competition_id,
                    CompetitionResult.team_id == team_id,
                )
            )
        ).scalar_one_or_none()

        if row is None:
            row = CompetitionResult(competition_id=competition_id, team_id=team_id)
            session.add(row)

        row.team_name = team_name
        row.final_score = final
        row.rank = rank
        row.award = _award_for(rank, total_teams)
        row.review_count = count
        row.status = ResultStatus.DRAFT.value
        results.append(row)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "成绩汇总冲突，请重试") from None

    await audit.record(
        session,
        action=AuditAction.UPDATE,
        object_type="CompetitionResult",
        object_id=competition_id,
        actor=admin,
        after={"computed": len(results), "skipped": len(skipped), "strategy": strategy},
    )

    results.sort(key=lambda r: (r.rank or 9999, r.team_id))
    return CalculateResponse(
        competition_id=competition_id,
        computed=len(results),
        skipped=skipped,
        results=[ResultOut.model_validate(r) for r in results],
    )


@router.post(
    "/competitions/{competition_id}/results/publish",
    response_model=list[ResultOut],
    summary="发布结果（FR-020）",
)
async def publish_results(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> list[ResultOut]:
    comp = await session.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "赛事不存在")
    if comp.state != CompetitionState.RESULT_PENDING.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "只有结果待发布状态可以发布结果，请先完成审查阶段迁移"
        )

    rows = (
        await session.execute(
            select(CompetitionResult)
            .where(CompetitionResult.competition_id == competition_id)
            .order_by(CompetitionResult.rank)
        )
    ).scalars().all()
    if not rows:
        raise HTTPException(status.HTTP_409_CONFLICT, "尚未汇总成绩，不能发布")

    now = datetime.now(UTC)
    for r in rows:
        r.status = ResultStatus.PUBLISHED.value
        r.published_at = now

    await audit.record(
        session,
        action=AuditAction.PUBLISH,
        object_type="CompetitionResult",
        object_id=competition_id,
        actor=admin,
        after={"published": len(rows)},
    )
    await session.flush()
    return [ResultOut.model_validate(r) for r in rows]


@router.get(
    "/competitions/{competition_id}/results",
    response_model=list[ResultOut],
    summary="查看结果（FR-021）",
)
async def list_results(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[ResultOut]:
    stmt = select(CompetitionResult).where(CompetitionResult.competition_id == competition_id)
    if user.role != Role.ADMIN.value:
        stmt = stmt.where(CompetitionResult.status == ResultStatus.PUBLISHED.value)
    rows = (await session.execute(stmt.order_by(CompetitionResult.rank))).scalars().all()

    if user.role in (Role.CAPTAIN.value, Role.MEMBER.value, Role.TEACHER.value):
        # 参赛方只能看自己队伍的结果
        my_teams = {
            m.team_id
            for m in (
                await session.execute(select(TeamMember).where(TeamMember.user_id == user.id))
            ).scalars().all()
        }
        rows = [r for r in rows if r.team_id in my_teams]

    return [ResultOut.model_validate(r) for r in rows]


@router.get(
    "/competitions/{competition_id}/results/all",
    response_model=list[ResultOut],
    summary="完整榜单（仅管理员）",
)
async def list_all_results(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(_admin),
) -> list[ResultOut]:
    rows = (
        await session.execute(
            select(CompetitionResult)
            .where(CompetitionResult.competition_id == competition_id)
            .order_by(CompetitionResult.rank)
        )
    ).scalars().all()
    return [ResultOut.model_validate(r) for r in rows]
