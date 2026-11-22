"""路由：赛事统计与平台概览（FR-026）。

统计口径集中写在本模块内：
- ADMIN 统计赛事全部数据（scope=ALL），result 含草稿成绩；
- TEACHER 仅统计本人以 ADVISOR 身份指导的队伍（scope=MY_TEAMS），
  且 result 只计入已发布(PUBLISHED)成绩，避免教师看到草稿分。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    EnrollmentStatus,
    ResultStatus,
    ReviewTaskStatus,
    Role,
    SubmissionStatus,
)
from app.core.deps import require_roles
from app.db.session import get_session
from app.models import (
    Competition,
    CompetitionResult,
    Enrollment,
    ReviewTask,
    Submission,
    Team,
    TeamMember,
    User,
)

router = APIRouter(tags=["统计"])

_admin = require_roles(Role.ADMIN)
_teacher = require_roles(Role.TEACHER)
# FR-026 赛事统计：ADMIN 与 TEACHER 均可读，内部按角色区分统计范围
_stats_reader = require_roles(Role.ADMIN, Role.TEACHER)

# 指导教师身份在 TeamMember.role_in_team 中的取值（见 TeamMemberRole.ADVISOR）
_ADVISOR_ROLE = "ADVISOR"


# ───────────────────── Pydantic schemas ─────────────────────
class EnrollmentStats(BaseModel):
    total: int = Field(0, description="统计范围内的报名总数")
    pending: int = Field(0, description="PENDING 状态报名数")
    approved: int = Field(0, description="仅统计 APPROVED 状态报名数")
    rejected: int = Field(0, description="REJECTED 状态报名数")
    needs_info: int = Field(0, description="NEEDS_INFO 状态报名数")


class SubmissionStats(BaseModel):
    total: int = Field(0, description="统计范围内的提交总数")
    draft: int = Field(0, description="DRAFT 状态提交数")
    submitted: int = Field(0, description="SUBMITTED 状态提交数")
    withdrawn: int = Field(0, description="WITHDRAWN 状态提交数")
    locked: int = Field(0, description="LOCKED 状态提交数")


class ReviewStats(BaseModel):
    total_tasks: int = Field(0, description="统计范围内的评审任务总数")
    assigned: int = Field(0, description="ASSIGNED 状态任务数")
    in_progress: int = Field(0, description="IN_PROGRESS 状态任务数")
    submitted: int = Field(0, description="SUBMITTED 状态任务数")
    overdue: int = Field(0, description="OVERDUE 状态任务数")
    replaced: int = Field(0, description="REPLACED 状态任务数")
    completion_rate: float = Field(
        0.0, description="submitted / total_tasks，保留 4 位小数；无任务时为 0.0"
    )


class ResultStats(BaseModel):
    total: int = Field(0, description="纳入统计的成绩记录数")
    draft: int = Field(0, description="DRAFT 状态成绩数（仅 ADMIN 视角可出现）")
    published: int = Field(0, description="PUBLISHED 状态成绩数")
    avg_final_score: float = Field(
        0.0, description="平均分保留 2 位；含草稿成绩，仅管理员可见完整分布；无数据为 0.0"
    )
    max_final_score: float = Field(0.0, description="最高分保留 2 位；无数据为 0.0")
    min_final_score: float = Field(0.0, description="最低分保留 2 位；无数据为 0.0")
    award_distribution: dict[str, int] = Field(
        default_factory=dict, description="按奖项名称汇总的获奖队伍数"
    )


class TeamStats(BaseModel):
    total: int = Field(0, description="统计范围内的队伍总数")
    with_submission: int = Field(0, description="已创建提交的队伍数")


class CompetitionStatisticsOut(BaseModel):
    competition_id: str = Field(..., description="赛事 ID")
    scope: Literal["ALL", "MY_TEAMS"] = Field(..., description="统计范围：管理员 ALL / 教师 MY_TEAMS")
    computed_at: datetime = Field(..., description="统计计算时间（UTC）")
    enrollment: EnrollmentStats
    submission: SubmissionStats
    review: ReviewStats
    result: ResultStats
    team: TeamStats
    notes: list[str] = Field(default_factory=list, description="统计口径说明")


class UsersOverview(BaseModel):
    total: int = Field(0, description="平台用户总数")
    by_role: dict[str, int] = Field(default_factory=dict, description="按角色(ADMIN/JUDGE/...)汇总")


class CompetitionsOverview(BaseModel):
    total: int = Field(0, description="平台赛事总数")
    by_state: dict[str, int] = Field(default_factory=dict, description="按赛事状态汇总")


class PlatformTotals(BaseModel):
    teams: int = Field(0, description="全平台队伍总数")
    submissions: int = Field(0, description="全平台提交总数")
    review_tasks: int = Field(0, description="全平台评审任务总数")
    published_results: int = Field(0, description="全平台已发布成绩总数")


class OverviewOut(BaseModel):
    users: UsersOverview
    competitions: CompetitionsOverview
    totals: PlatformTotals


# ───────────────────── 赛事统计（FR-026）─────────────────────
@router.get(
    "/competitions/{competition_id}/statistics",
    response_model=CompetitionStatisticsOut,
    summary="赛事统计（FR-026）",
)
async def competition_statistics(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(_stats_reader),
) -> CompetitionStatisticsOut:
    comp = await session.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "赛事不存在")

    is_admin = user.role == Role.ADMIN.value
    scope: Literal["ALL", "MY_TEAMS"] = "ALL" if is_admin else "MY_TEAMS"

    # 教师范围：本人以 ADVISOR 身份指导的队伍集合；ADMIN 用 None 表示全部
    scoped_team_ids: set[str] | None = None
    if not is_admin:
        member_rows = (
            await session.execute(
                select(TeamMember).where(
                    TeamMember.user_id == user.id,
                    TeamMember.role_in_team == _ADVISOR_ROLE,
                )
            )
        ).scalars().all()
        scoped_team_ids = {m.team_id for m in member_rows}

    # ── 报名 ──
    enr_stmt = select(Enrollment).where(Enrollment.competition_id == competition_id)
    if scoped_team_ids is not None:
        enr_stmt = enr_stmt.where(Enrollment.team_id.in_(scoped_team_ids))
    enrollments = (await session.execute(enr_stmt)).scalars().all()

    def _enr_count(value: str) -> int:
        return sum(1 for e in enrollments if e.status == value)

    enrollment_stats = EnrollmentStats(
        total=len(enrollments),
        pending=_enr_count(EnrollmentStatus.PENDING.value),
        approved=_enr_count(EnrollmentStatus.APPROVED.value),
        rejected=_enr_count(EnrollmentStatus.REJECTED.value),
        needs_info=_enr_count(EnrollmentStatus.NEEDS_INFO.value),
    )

    # ── 提交（通过报名关联到队伍范围）──
    enrollment_ids = [e.id for e in enrollments]
    submissions = (
        await session.execute(
            select(Submission).where(Submission.enrollment_id.in_(enrollment_ids))
        )
    ).scalars().all()

    def _sub_count(value: str) -> int:
        return sum(1 for s in submissions if s.status == value)

    submission_stats = SubmissionStats(
        total=len(submissions),
        draft=_sub_count(SubmissionStatus.DRAFT.value),
        submitted=_sub_count(SubmissionStatus.SUBMITTED.value),
        withdrawn=_sub_count(SubmissionStatus.WITHDRAWN.value),
        locked=_sub_count(SubmissionStatus.LOCKED.value),
    )

    # ── 评审任务（通过提交关联到队伍范围）──
    submission_ids = [s.id for s in submissions]
    task_stmt = select(ReviewTask).where(ReviewTask.competition_id == competition_id)
    if submission_ids:
        task_stmt = task_stmt.where(ReviewTask.submission_id.in_(submission_ids))
    else:
        task_stmt = task_stmt.where(False)  # 范围内无提交 -> 无任务
    tasks = (await session.execute(task_stmt)).scalars().all()

    def _task_count(value: str) -> int:
        return sum(1 for t in tasks if t.status == value)

    total_tasks = len(tasks)
    submitted_tasks = _task_count(ReviewTaskStatus.SUBMITTED.value)
    completion_rate = round(submitted_tasks / total_tasks, 4) if total_tasks else 0.0
    review_stats = ReviewStats(
        total_tasks=total_tasks,
        assigned=_task_count(ReviewTaskStatus.ASSIGNED.value),
        in_progress=_task_count(ReviewTaskStatus.IN_PROGRESS.value),
        submitted=submitted_tasks,
        overdue=_task_count(ReviewTaskStatus.OVERDUE.value),
        replaced=_task_count(ReviewTaskStatus.REPLACED.value),
        completion_rate=completion_rate,
    )

    # ── 成绩 ──
    result_stmt = select(CompetitionResult).where(
        CompetitionResult.competition_id == competition_id
    )
    if scoped_team_ids is not None:
        result_stmt = result_stmt.where(
            CompetitionResult.team_id.in_(scoped_team_ids),
            CompetitionResult.status == ResultStatus.PUBLISHED.value,
        )
    results = (await session.execute(result_stmt)).scalars().all()

    scores = [r.final_score for r in results]
    award_dist: dict[str, int] = {}
    for r in results:
        if r.award:
            award_dist[r.award] = award_dist.get(r.award, 0) + 1
    result_stats = ResultStats(
        total=len(results),
        draft=sum(1 for r in results if r.status == ResultStatus.DRAFT.value),
        published=sum(1 for r in results if r.status == ResultStatus.PUBLISHED.value),
        avg_final_score=round(sum(scores) / len(scores), 2) if scores else 0.0,
        max_final_score=round(max(scores), 2) if scores else 0.0,
        min_final_score=round(min(scores), 2) if scores else 0.0,
        award_distribution=award_dist,
    )

    # ── 队伍 ──
    team_stmt = select(Team).where(Team.competition_id == competition_id)
    if scoped_team_ids is not None:
        team_stmt = team_stmt.where(Team.id.in_(scoped_team_ids))
    teams = (await session.execute(team_stmt)).scalars().all()
    submitted_enrollment_ids = {s.enrollment_id for s in submissions}
    with_submission = sum(1 for e in enrollments if e.id in submitted_enrollment_ids)
    team_stats = TeamStats(total=len(teams), with_submission=with_submission)

    notes = [
        "approved 仅统计 APPROVED 状态报名，其余状态分别计入 pending/rejected/needs_info",
        "avg_final_score 含草稿成绩，仅管理员可见完整分布；教师视角仅计入已发布(PUBLISHED)成绩",
        "completion_rate = 已提交(SUBMITTED)评审任务数 / 任务总数，保留 4 位小数",
        "管理员(ADMIN)统计全部赛事数据(scope=ALL)；教师(TEACHER)仅统计本人以 ADVISOR 身份指导的队伍(scope=MY_TEAMS)",
    ]

    return CompetitionStatisticsOut(
        competition_id=competition_id,
        scope=scope,
        computed_at=datetime.now(UTC),
        enrollment=enrollment_stats,
        submission=submission_stats,
        review=review_stats,
        result=result_stats,
        team=team_stats,
        notes=notes,
    )


# ───────────────────── 平台概览（FR-026）─────────────────────
@router.get(
    "/statistics/overview",
    response_model=OverviewOut,
    summary="平台统计概览（FR-026，仅管理员）",
)
async def platform_overview(
    session: AsyncSession = Depends(get_session),
    _admin_user: User = Depends(_admin),
) -> OverviewOut:
    user_rows = (
        await session.execute(select(User.role, func.count(User.id)).group_by(User.role))
    ).all()
    by_role = {role: int(count) for role, count in user_rows}

    comp_rows = (
        await session.execute(select(Competition.state, func.count(Competition.id)).group_by(Competition.state))
    ).all()
    by_state = {state: int(count) for state, count in comp_rows}

    teams = (await session.execute(select(func.count(Team.id)))).scalar() or 0
    submissions = (await session.execute(select(func.count(Submission.id)))).scalar() or 0
    review_tasks = (await session.execute(select(func.count(ReviewTask.id)))).scalar() or 0
    published_results = (
        await session.execute(
            select(func.count(CompetitionResult.id)).where(
                CompetitionResult.status == ResultStatus.PUBLISHED.value
            )
        )
    ).scalar() or 0

    return OverviewOut(
        users=UsersOverview(total=sum(by_role.values()), by_role=by_role),
        competitions=CompetitionsOverview(total=sum(by_state.values()), by_state=by_state),
        totals=PlatformTotals(
            teams=int(teams),
            submissions=int(submissions),
            review_tasks=int(review_tasks),
            published_results=int(published_results),
        ),
    )
