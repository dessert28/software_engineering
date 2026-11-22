"""路由：评审（FR-012～FR-016）。

匿名评审的实现要点：
- 每张任务有独立的 material_ref，专家端只能看到这个串；
- 材料接口不返回队伍名、学校、指导教师、队员姓名；
- 映射关系只在管理员视角可读。
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    RUBRIC_ITEMS,
    AuditAction,
    CompetitionState,
    ReviewTaskStatus,
    Role,
    ScoreAuthority,
)
from app.core.deps import PRIVILEGED_REVIEW_ROLES, get_current_user, require_roles
from app.core.security import hash_password
from app.db.session import get_session
from app.models import (
    BlobObject,
    Competition,
    Enrollment,
    ReviewTask,
    ScoreRecord,
    Submission,
    SubmissionVersion,
    Team,
    TeamMember,
    User,
)
from app.schemas import (
    AnonymousMaterial,
    JudgeCreate,
    ReviewProgress,
    ReviewTaskCreate,
    ReviewTaskOut,
    ScoreOut,
    ScoreSubmit,
    UserOut,
)
from app.services import audit
from app.services.rules import (
    compute_total,
    mark_overdue,
    parse_rubric,
)

router = APIRouter(tags=["评审"])

_admin = require_roles(Role.ADMIN)
_judge = require_roles(*PRIVILEGED_REVIEW_ROLES)


# ───────────────────── 专家管理（FR-012）─────────────────────
@router.post("/judges", response_model=UserOut, status_code=201, summary="新增评审专家")
async def create_judge(
    payload: JudgeCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> UserOut:
    dup = (
        await session.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, "该邮箱已存在")

    judge = User(
        email=payload.email,
        name=payload.name,
        role=Role.JUDGE.value,
        school=payload.school,
        expertise=payload.expertise,
        password_hash=hash_password(payload.password),
        can_review=True,
    )
    session.add(judge)
    await session.flush()
    await audit.record(
        session,
        action=AuditAction.CREATE,
        object_type="User",
        object_id=judge.id,
        actor=admin,
        after={"email": judge.email, "role": judge.role},
    )
    return UserOut.model_validate(judge)


@router.get("/judges", response_model=list[UserOut], summary="专家列表")
async def list_judges(
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(_admin),
) -> list[UserOut]:
    rows = (
        await session.execute(select(User).where(User.role == Role.JUDGE.value).order_by(User.name))
    ).scalars().all()
    return [UserOut.model_validate(u) for u in rows]


@router.patch("/judges/{judge_id}/availability", response_model=UserOut, summary="启用/停用专家")
async def set_judge_availability(
    judge_id: str,
    can_review: bool,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> UserOut:
    judge = await session.get(User, judge_id)
    if judge is None or judge.role != Role.JUDGE.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "专家不存在")
    before = {"can_review": judge.can_review}
    judge.can_review = can_review
    await audit.record(
        session,
        action=AuditAction.UPDATE,
        object_type="User",
        object_id=judge.id,
        actor=admin,
        before=before,
        after={"can_review": can_review},
    )
    return UserOut.model_validate(judge)


# ───────────────────── 任务分配（FR-013）─────────────────────
@router.post("/review-tasks", response_model=ReviewTaskOut, status_code=201, summary="分配评审任务")
async def create_review_task(
    payload: ReviewTaskCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> ReviewTaskOut:
    comp = await session.get(Competition, payload.competition_id)
    if comp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "赛事不存在")
    if comp.state not in (
        CompetitionState.SUBMISSION_CLOSED.value,
        CompetitionState.REVIEWING.value,
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "只有提交截止后才能分配评审任务")

    sub = await session.get(Submission, payload.submission_id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "提交记录不存在")
    enr = await session.get(Enrollment, sub.enrollment_id)
    if enr is None or enr.competition_id != payload.competition_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该提交不属于此赛事")

    reviewer = await session.get(User, payload.reviewer_id)
    if reviewer is None or reviewer.role != Role.JUDGE.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "评审专家不存在")
    if not reviewer.can_review:
        raise HTTPException(status.HTTP_409_CONFLICT, "该专家已停用，不能接收新任务")

    # 回避关系：专家不能评审本校队伍（初版规则，可在 RuleProfile 中扩展）
    team = await session.get(Team, enr.team_id)
    if team and reviewer.school and team.school and reviewer.school == team.school:
        raise HTTPException(status.HTTP_409_CONFLICT, "回避冲突：专家不能评审本校队伍")

    task = ReviewTask(
        competition_id=payload.competition_id,
        submission_id=payload.submission_id,
        reviewer_id=payload.reviewer_id,
        rubric_id=None,
        status=ReviewTaskStatus.ASSIGNED.value,
        due_at=payload.due_at,
        material_ref=uuid.uuid4().hex[:12].upper(),
    )
    session.add(task)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "该专家已被分配此提交，不能重复分配") from None

    await audit.record(
        session,
        action=AuditAction.CREATE,
        object_type="ReviewTask",
        object_id=task.id,
        actor=admin,
        after={"submission_id": payload.submission_id, "reviewer_id": payload.reviewer_id},
    )
    return ReviewTaskOut.model_validate(task)


@router.get("/review-tasks/mine", response_model=list[ReviewTaskOut], summary="我的评审任务")
async def my_tasks(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(_judge),
) -> list[ReviewTaskOut]:
    rows = (
        await session.execute(
            select(ReviewTask)
            .where(ReviewTask.reviewer_id == user.id)
            .order_by(ReviewTask.created_at)
        )
    ).scalars().all()
    mark_overdue(rows)
    await session.flush()
    return [ReviewTaskOut.model_validate(t) for t in rows]


@router.get(
    "/review-tasks/{task_id}/material",
    response_model=AnonymousMaterial,
    summary="读取匿名材料（FR-014）",
)
async def read_material(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(_judge),
) -> AnonymousMaterial:
    task = await session.get(ReviewTask, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if task.reviewer_id != user.id and user.role != Role.ADMIN.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "不是你的评审任务")

    sub = await session.get(Submission, task.submission_id)
    assert sub is not None
    comp = await session.get(Competition, task.competition_id)
    assert comp is not None

    version: SubmissionVersion | None = None
    if sub.current_version_id:
        version = await session.get(SubmissionVersion, sub.current_version_id)

    blob: BlobObject | None = None
    if version:
        blob = await session.get(BlobObject, version.blob_id)

    rubric = parse_rubric(comp.rule_profile, RUBRIC_ITEMS)

    # 只返回匿名化字段：无队伍名、学校、成员、指导教师
    return AnonymousMaterial(
        task_id=task.id,
        competition_title=comp.title,
        problem_code=f"作品编号 {task.material_ref}",
        version_no=version.version_no if version else 0,
        file_name=blob.original_name if blob else None,
        file_size=blob.size_bytes if blob else None,
        note=version.note if version else None,
        rubric=rubric,
    )


# ───────────────────── 评分（FR-015）─────────────────────
@router.post("/review-tasks/{task_id}/score", response_model=ScoreOut, summary="提交评分")
async def submit_score(
    task_id: str,
    payload: ScoreSubmit,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(_judge),
) -> ScoreOut:
    task = await session.get(ReviewTask, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if task.reviewer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "不是你的评审任务")
    if task.status in (ReviewTaskStatus.SUBMITTED.value,):
        raise HTTPException(status.HTTP_409_CONFLICT, "该任务已评分，不能重复提交")

    comp = await session.get(Competition, task.competition_id)
    assert comp is not None
    rubric = parse_rubric(comp.rule_profile, RUBRIC_ITEMS)

    # 必填项校验：评语至少 10 字
    if not payload.comment or len(payload.comment.strip()) < 10:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "评语不少于 10 字")

    total = compute_total(payload.dimension, rubric)

    record = ScoreRecord(
        task_id=task.id,
        reviewer_id=user.id,
        dimension_json=json.dumps(payload.dimension, ensure_ascii=False),
        total_score=total,
        comment=payload.comment,
        authority=ScoreAuthority.HUMAN.value,
        is_final=True,
    )
    session.add(record)

    task.status = ReviewTaskStatus.SUBMITTED.value

    await audit.record(
        session,
        action=AuditAction.SCORE,
        object_type="ScoreRecord",
        object_id=record.id,
        actor=user,
        after={"task_id": task.id, "total": total},
    )
    await session.flush()
    return ScoreOut.model_validate(record)


# ───────────────────── 进度（FR-016）─────────────────────
@router.get(
    "/competitions/{competition_id}/review-progress",
    response_model=ReviewProgress,
    summary="评审进度看板",
)
async def review_progress(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(_admin),
) -> ReviewProgress:
    rows = (
        await session.execute(
            select(ReviewTask).where(ReviewTask.competition_id == competition_id)
        )
    ).scalars().all()

    mark_overdue(rows)
    await session.flush()

    counts = {s.value: 0 for s in ReviewTaskStatus}
    for t in rows:
        counts[t.status] = counts.get(t.status, 0) + 1

    total = len(rows)
    done = counts[ReviewTaskStatus.SUBMITTED.value]
    return ReviewProgress(
        competition_id=competition_id,
        total_tasks=total,
        submitted=done,
        in_progress=counts[ReviewTaskStatus.IN_PROGRESS.value],
        assigned=counts[ReviewTaskStatus.ASSIGNED.value],
        overdue=counts[ReviewTaskStatus.OVERDUE.value],
        completion_rate=round(done / total, 4) if total else 0.0,
    )


@router.get(
    "/competitions/{competition_id}/review-tasks",
    response_model=list[ReviewTaskOut],
    summary="赛事全部评审任务（管理员视角）",
)
async def list_tasks(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(_admin),
) -> list[ReviewTaskOut]:
    rows = (
        await session.execute(
            select(ReviewTask)
            .where(ReviewTask.competition_id == competition_id)
            .order_by(ReviewTask.created_at)
        )
    ).scalars().all()
    return [ReviewTaskOut.model_validate(t) for t in rows]
