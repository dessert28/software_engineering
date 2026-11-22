"""路由：评审异常与复核（FR-017 / FR-018）。

两条核心纪律：
- 异常处理全程留痕（audit EXCEPTION），替换专家时仍执行同校回避与重复分配校验；
- 复核绝不改动原始 ScoreRecord：原始评分先冻结成快照，复核结果另存为
  authority=REVIEW 的记录，二者在读取接口中明确区分。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    RUBRIC_ITEMS,
    AuditAction,
    RecheckStatus,
    ReviewExceptionStatus,
    ReviewExceptionType,
    ReviewTaskStatus,
    Role,
)
from app.core.deps import get_current_user, require_roles
from app.db.session import get_session
from app.models import (
    Competition,
    Enrollment,
    Recheck,
    ReviewException,
    ReviewTask,
    ScoreRecord,
    Team,
    User,
)
from app.services import audit
from app.services.rules import compute_total, parse_rubric

router = APIRouter(tags=["评审异常与复核"])

_admin = require_roles(Role.ADMIN)

_ALLOWED_ACTIONS = {"REPLACE", "EXTEND", "MANUAL"}


# ───────────────────── 本地 Schema ─────────────────────
class _ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ExceptionCreate(BaseModel):
    exception_type: ReviewExceptionType
    reason: str = Field(min_length=5)
    action: str | None = None
    due_at: datetime | None = None

    @field_validator("action")
    @classmethod
    def _action_ok(cls, v: str | None) -> str | None:
        if v is not None and v not in _ALLOWED_ACTIONS:
            raise ValueError("action 只能是 REPLACE/EXTEND/MANUAL")
        return v


class ExceptionOut(_ORMModel):
    id: str
    competition_id: str
    task_id: str
    exception_type: str
    reason: str
    action: str | None
    status: str
    created_by: str | None
    handled_by: str | None
    handled_at: datetime | None
    handling_note: str | None
    created_at: datetime


class ExceptionResolve(BaseModel):
    action: str
    handling_note: str
    replacement_reviewer_id: str | None = None
    due_at: datetime | None = None

    @field_validator("action")
    @classmethod
    def _action_ok(cls, v: str) -> str:
        if v not in _ALLOWED_ACTIONS:
            raise ValueError("action 只能是 REPLACE/EXTEND/MANUAL")
        return v


class TaskBrief(_ORMModel):
    id: str
    competition_id: str
    submission_id: str
    reviewer_id: str
    status: ReviewTaskStatus
    due_at: datetime | None
    material_ref: str


class ResolveOut(BaseModel):
    exception: ExceptionOut
    new_task: TaskBrief | None = None


class RecheckCreate(BaseModel):
    task_id: str
    reason: str = Field(min_length=5)


class RecheckOut(_ORMModel):
    id: str
    competition_id: str
    task_id: str
    original_score_id: str
    frozen_original_json: str
    reason: str
    status: str
    revised_dimension_json: str | None
    revised_total: float | None
    comment: str | None
    reviewer_id: str | None
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime


class RecheckDecide(BaseModel):
    dimension: dict[str, float]
    comment: str = Field(min_length=10)

    @field_validator("dimension")
    @classmethod
    def _non_empty(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("维度分不能为空")
        for key, val in v.items():
            if not (0 <= val <= 100):
                raise ValueError(f"维度 {key} 的分数必须在 0～100 之间")
        return v


class ScoreBrief(_ORMModel):
    id: str
    task_id: str
    reviewer_id: str
    dimension_json: str
    total_score: float
    comment: str | None
    authority: str
    is_final: bool


class RecheckDetail(BaseModel):
    recheck: RecheckOut
    original: ScoreBrief


# ───────────────────── FR-017：评审异常 ─────────────────────
@router.post(
    "/review-tasks/{task_id}/exceptions",
    response_model=ExceptionOut,
    status_code=201,
    summary="标记评审异常",
)
async def create_exception(
    task_id: str,
    payload: ExceptionCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> ExceptionOut:
    task = await session.get(ReviewTask, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "评审任务不存在")

    # EXTEND 必须同时给出新的截止时间，否则延期无从落地
    if payload.action == "EXTEND" and payload.due_at is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "EXTEND 操作必须提供 due_at")

    exc = ReviewException(
        competition_id=task.competition_id,
        task_id=task.id,
        exception_type=payload.exception_type.value,
        reason=payload.reason,
        action=payload.action,
        status=ReviewExceptionStatus.OPEN.value,
        created_by=admin.id,
    )
    session.add(exc)

    if payload.action == "EXTEND":
        task.due_at = payload.due_at
    elif payload.action == "REPLACE":
        task.status = ReviewTaskStatus.REPLACED.value
    # MANUAL 只记录，不改任务

    await audit.record(
        session,
        action=AuditAction.EXCEPTION,
        object_type="ReviewException",
        object_id=exc.id,
        actor=admin,
        after={
            "task_id": task.id,
            "exception_type": exc.exception_type,
            "action": payload.action,
        },
        reason=payload.reason,
    )
    await session.flush()
    return ExceptionOut.model_validate(exc)


@router.get(
    "/competitions/{competition_id}/review-exceptions",
    response_model=list[ExceptionOut],
    summary="赛事评审异常列表",
)
async def list_exceptions(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(_admin),
) -> list[ExceptionOut]:
    rows = (
        await session.execute(
            select(ReviewException)
            .where(ReviewException.competition_id == competition_id)
            .order_by(ReviewException.created_at.desc())
        )
    ).scalars().all()
    return [ExceptionOut.model_validate(r) for r in rows]


@router.post(
    "/review-exceptions/{exception_id}/resolve",
    response_model=ResolveOut,
    summary="处理评审异常",
)
async def resolve_exception(
    exception_id: str,
    payload: ExceptionResolve,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> ResolveOut:
    exc = await session.get(ReviewException, exception_id)
    if exc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "评审异常不存在")
    if exc.status != ReviewExceptionStatus.OPEN.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "该异常已处理，不能重复处理")

    task = await session.get(ReviewTask, exc.task_id)
    if task is None:  # 异常记录指向的任务被删除，属于数据不一致
        raise HTTPException(status.HTTP_404_NOT_FOUND, "关联的评审任务不存在")

    new_task: ReviewTask | None = None

    if payload.action == "REPLACE":
        if not payload.replacement_reviewer_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "REPLACE 操作必须提供 replacement_reviewer_id")

        replacement = await session.get(User, payload.replacement_reviewer_id)
        if replacement is None or replacement.role != Role.JUDGE.value:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "替换专家不存在或不是评审专家")
        if not replacement.can_review:
            raise HTTPException(status.HTTP_409_CONFLICT, "该专家已停用，不能接收新任务")

        # 同校回避：沿用分配任务时的规则（专家不能评审本校队伍）
        enrollment_id = await _enrollment_for_submission(session, task.submission_id)
        enr = await session.get(Enrollment, enrollment_id) if enrollment_id else None
        if enr is not None:
            team = await session.get(Team, enr.team_id)
            if (
                team is not None
                and replacement.school
                and team.school
                and replacement.school == team.school
            ):
                raise HTTPException(status.HTTP_409_CONFLICT, "回避冲突：替换专家不能评审本校队伍")

        # 重复分配：同一 submission + 同一 reviewer 只能有一条任务
        dup = (
            await session.execute(
                select(ReviewTask).where(
                    ReviewTask.submission_id == task.submission_id,
                    ReviewTask.reviewer_id == replacement.id,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "该专家已被分配此提交，不能重复分配")

        task.status = ReviewTaskStatus.REPLACED.value
        new_task = ReviewTask(
            competition_id=task.competition_id,
            submission_id=task.submission_id,
            reviewer_id=replacement.id,
            rubric_id=None,
            status=ReviewTaskStatus.ASSIGNED.value,
            due_at=payload.due_at,
            material_ref=uuid.uuid4().hex[:12].upper(),
        )
        session.add(new_task)
    elif payload.action == "EXTEND":
        if payload.due_at is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "EXTEND 操作必须提供 due_at")
        task.due_at = payload.due_at
    # MANUAL 只记录处理说明

    exc.status = ReviewExceptionStatus.RESOLVED.value
    exc.handled_by = admin.id
    exc.handled_at = datetime.now(UTC)
    exc.handling_note = payload.handling_note

    await audit.record(
        session,
        action=AuditAction.EXCEPTION,
        object_type="ReviewException",
        object_id=exc.id,
        actor=admin,
        before={"status": ReviewExceptionStatus.OPEN.value},
        after={"status": exc.status, "action": payload.action},
        reason=payload.handling_note,
    )
    await session.flush()
    return ResolveOut(
        exception=ExceptionOut.model_validate(exc),
        new_task=TaskBrief.model_validate(new_task) if new_task is not None else None,
    )


async def _enrollment_for_submission(session: AsyncSession, submission_id: str) -> str | None:
    """取提交记录对应的报名 ID（回避校验需要沿此链路找到队伍）。"""
    from app.models import Submission

    sub = await session.get(Submission, submission_id)
    return sub.enrollment_id if sub is not None else None


# ───────────────────── FR-018：评审复核 ─────────────────────
@router.post(
    "/competitions/{competition_id}/rechecks",
    response_model=RecheckOut,
    status_code=201,
    summary="发起评审复核",
)
async def create_recheck(
    competition_id: str,
    payload: RecheckCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> RecheckOut:
    comp = await session.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "赛事不存在")

    task = await session.get(ReviewTask, payload.task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "评审任务不存在")
    if task.competition_id != competition_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该评审任务不属于此赛事")

    score = (
        await session.execute(
            select(ScoreRecord).where(
                ScoreRecord.task_id == task.id,
                ScoreRecord.is_final.is_(True),
            )
        )
    ).scalars().first()
    if score is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "该任务没有可复核的最终评分")

    exists = (
        await session.execute(
            select(Recheck).where(Recheck.original_score_id == score.id)
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "该评分已发起过复核")

    # 冻结原始评分快照：之后无论发生什么，都不再改动原始 ScoreRecord
    frozen = json.dumps(
        {
            "dimension_json": score.dimension_json,
            "total_score": score.total_score,
            "comment": score.comment,
            "authority": score.authority,
        },
        ensure_ascii=False,
    )
    recheck = Recheck(
        competition_id=competition_id,
        task_id=task.id,
        original_score_id=score.id,
        frozen_original_json=frozen,
        reason=payload.reason,
        status=RecheckStatus.PENDING.value,
    )
    session.add(recheck)

    await audit.record(
        session,
        action=AuditAction.RECHECK,
        object_type="Recheck",
        object_id=recheck.id,
        actor=admin,
        after={"task_id": task.id, "original_score_id": score.id},
        reason=payload.reason,
    )
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "该评分已发起过复核") from None
    return RecheckOut.model_validate(recheck)


@router.get(
    "/competitions/{competition_id}/rechecks",
    response_model=list[RecheckOut],
    summary="赛事复核列表",
)
async def list_rechecks(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(_admin),
) -> list[RecheckOut]:
    rows = (
        await session.execute(
            select(Recheck)
            .where(Recheck.competition_id == competition_id)
            .order_by(Recheck.created_at.desc())
        )
    ).scalars().all()
    return [RecheckOut.model_validate(r) for r in rows]


@router.post(
    "/rechecks/{recheck_id}/decide",
    response_model=RecheckOut,
    summary="作出复核结论",
)
async def decide_recheck(
    recheck_id: str,
    payload: RecheckDecide,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RecheckOut:
    recheck = await session.get(Recheck, recheck_id)
    if recheck is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "复核记录不存在")
    if recheck.status != RecheckStatus.PENDING.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "该复核已处理，不能重复复核")

    is_admin = user.role == Role.ADMIN.value
    if not is_admin and recheck.reviewer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只有管理员或指定复核专家可作出复核结论")

    comp = await session.get(Competition, recheck.competition_id)
    rubric = parse_rubric(comp.rule_profile, RUBRIC_ITEMS) if comp else RUBRIC_ITEMS
    revised_total = compute_total(payload.dimension, rubric)

    # 复核结果另存于 Recheck，原始 ScoreRecord 绝不修改
    if recheck.reviewer_id is None:
        recheck.reviewer_id = user.id
    recheck.revised_dimension_json = json.dumps(payload.dimension, ensure_ascii=False)
    recheck.revised_total = revised_total
    recheck.comment = payload.comment
    recheck.status = RecheckStatus.COMPLETED.value
    recheck.decided_by = user.id
    recheck.decided_at = datetime.now(UTC)

    await audit.record(
        session,
        action=AuditAction.RECHECK,
        object_type="Recheck",
        object_id=recheck.id,
        actor=user,
        before={"status": RecheckStatus.PENDING.value},
        after={"status": recheck.status, "revised_total": revised_total},
        reason=payload.comment,
    )
    await session.flush()
    return RecheckOut.model_validate(recheck)


@router.get(
    "/rechecks/{recheck_id}",
    response_model=RecheckDetail,
    summary="复核详情（原始评分与复核结果分列）",
)
async def get_recheck(
    recheck_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RecheckDetail:
    recheck = await session.get(Recheck, recheck_id)
    if recheck is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "复核记录不存在")

    if user.role != Role.ADMIN.value:
        original = await session.get(ScoreRecord, recheck.original_score_id)
        related = {recheck.reviewer_id}
        if original is not None:
            related.add(original.reviewer_id)
        if user.id not in related:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "无权查看该复核记录")

    original = await session.get(ScoreRecord, recheck.original_score_id)
    if original is None:  # 原始评分被物理删除，属于数据不一致
        raise HTTPException(status.HTTP_404_NOT_FOUND, "原始评分记录不存在")

    return RecheckDetail(
        recheck=RecheckOut.model_validate(recheck),
        original=ScoreBrief.model_validate(original),
    )
