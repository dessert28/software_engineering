"""路由：AI 预评级与确定性分流（FR-029~031）。

设计要点：
- 评估与分流引擎全部在 app.services.ai，本模块只做鉴权、参数校验、查询编排与响应整形；
- 专家端只读风险标记，绝不返回分数/置信度/维度证据（防锚定）；
- 响应 schema 本地定义，避免污染公共 schemas 包。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    AIReviewStatus,
    AuditAction,
    EscalationStatus,
    Role,
    SubmissionStatus,
)
from app.core.deps import PRIVILEGED_REVIEW_ROLES, get_current_user, require_roles
from app.db.session import get_session
from app.models import (
    AIReviewRecord,
    Competition,
    Enrollment,
    ReviewEscalation,
    ReviewTask,
    Submission,
    SubmissionVersion,
    User,
)
from app.services import ai, audit

router = APIRouter(tags=["AI 预评级"])

_admin = require_roles(Role.ADMIN)
_judge = require_roles(*PRIVILEGED_REVIEW_ROLES)


# ───────────────────── 本地响应 schema ─────────────────────
class RiskFlagOut(BaseModel):
    code: str
    detail: str


class AIReviewOut(BaseModel):
    id: str
    version_id: str
    suggested_score: float | None = None
    confidence: float | None = None
    evaluation_level: str
    status: str
    risk_flags: list[RiskFlagOut] = Field(default_factory=list)
    authority: str
    level_reason: str | None = None
    error_message: str | None = None
    rule_version: str | None = None
    assessed_at: datetime | None = None
    created_at: datetime


class AssessSummary(BaseModel):
    total: int
    succeeded: int
    skipped: int
    failed: int
    records: list[AIReviewOut] = Field(default_factory=list)


class ReviewRiskFlagsOut(BaseModel):
    """专家端专用：只含风险标记，严禁出现分数/置信度/维度证据字段。"""

    task_id: str
    status: str
    risk_flags: list[RiskFlagOut] = Field(default_factory=list)
    notice: str


class EscalationOut(BaseModel):
    id: str
    competition_id: str
    submission_id: str
    rule_code: str
    rule_version: str
    thresholds: dict[str, Any] = Field(default_factory=dict)
    observed: dict[str, Any] = Field(default_factory=dict)
    action: str
    status: str
    note: str | None = None
    handled_at: datetime | None = None
    created_at: datetime


class EscalationHandleIn(BaseModel):
    status: Literal["RESOLVED", "DISMISSED"]
    note: str = Field(min_length=2)


# ───────────────────── 整形工具 ─────────────────────
def _parse_risk_flags(raw: str | None) -> list[RiskFlagOut]:
    """把 AIReviewRecord.risk_flags_json 解析为响应模型；脏数据按空列表降级。"""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[RiskFlagOut] = []
    for item in data:
        if isinstance(item, dict):
            out.append(
                RiskFlagOut(code=str(item.get("code", "")), detail=str(item.get("detail", "")))
            )
    return out


def _review_out(record: AIReviewRecord) -> AIReviewOut:
    return AIReviewOut(
        id=record.id,
        version_id=record.version_id,
        suggested_score=record.suggested_score,
        confidence=record.confidence,
        evaluation_level=record.evaluation_level,
        status=record.status,
        risk_flags=_parse_risk_flags(record.risk_flags_json),
        authority=record.authority,
        level_reason=record.level_reason,
        error_message=record.error_message,
        rule_version=record.rule_version,
        assessed_at=record.assessed_at,
        created_at=record.created_at,
    )


def _escalation_out(row: ReviewEscalation) -> EscalationOut:
    try:
        thresholds = json.loads(row.thresholds_json or "{}")
    except (json.JSONDecodeError, TypeError):
        thresholds = {}
    try:
        observed = json.loads(row.observed_json or "{}")
    except (json.JSONDecodeError, TypeError):
        observed = {}
    return EscalationOut(
        id=row.id,
        competition_id=row.competition_id,
        submission_id=row.submission_id,
        rule_code=row.rule_code,
        rule_version=row.rule_version,
        thresholds=thresholds if isinstance(thresholds, dict) else {},
        observed=observed if isinstance(observed, dict) else {},
        action=row.action,
        status=row.status,
        note=row.note,
        handled_at=row.handled_at,
        created_at=row.created_at,
    )


async def _get_competition_or_404(session: AsyncSession, competition_id: str) -> Competition:
    comp = await session.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "赛事不存在")
    return comp


async def _competition_of_submission(
    session: AsyncSession, submission: Submission
) -> Competition:
    enrollment = await session.get(Enrollment, submission.enrollment_id)
    if enrollment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "报名记录不存在")
    comp = await session.get(Competition, enrollment.competition_id)
    if comp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "赛事不存在")
    return comp


# ───────────────────── 1. 批量预评级 ─────────────────────
@router.post(
    "/competitions/{competition_id}/ai/assess",
    response_model=AssessSummary,
    summary="批量 AI 预评级（管理员）",
)
async def assess_competition(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> AssessSummary:
    comp = await _get_competition_or_404(session, competition_id)

    # 提交通过报名关联到赛事（Submission 本身没有 competition_id 列）
    submissions = (
        await session.execute(
            select(Submission)
            .join(Enrollment, Submission.enrollment_id == Enrollment.id)
            .where(
                Enrollment.competition_id == competition_id,
                Submission.status.in_(
                    (SubmissionStatus.SUBMITTED.value, SubmissionStatus.LOCKED.value)
                ),
            )
            .order_by(Submission.created_at)
        )
    ).scalars().all()

    records: list[AIReviewRecord] = []
    seen: set[str] = set()
    total = 0
    succeeded = skipped = failed = 0

    for submission in submissions:
        if not submission.current_version_id:
            continue
        total += 1
        try:
            record = await ai.assess_version(
                session, submission.current_version_id, comp, admin
            )
        except LookupError:
            # 版本/文件对象缺失属于脏数据，按失败降级，不阻断整批
            failed += 1
            continue
        if record.id not in seen:
            seen.add(record.id)
            records.append(record)
        if record.status == AIReviewStatus.SUCCEEDED.value:
            succeeded += 1
        elif record.status == AIReviewStatus.SKIPPED.value:
            skipped += 1
        else:
            failed += 1

    return AssessSummary(
        total=total,
        succeeded=succeeded,
        skipped=skipped,
        failed=failed,
        records=[_review_out(r) for r in records],
    )


# ───────────────────── 2. 单作品预评级 ─────────────────────
@router.post(
    "/submissions/{submission_id}/ai-assessment",
    response_model=AIReviewOut,
    summary="单作品 AI 预评级（管理员可见分数）",
)
async def assess_submission(
    submission_id: str,
    version_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> AIReviewOut:
    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "提交记录不存在")

    target_version_id = version_id or submission.current_version_id
    if not target_version_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "提交没有可评估的版本")

    version = await session.get(SubmissionVersion, target_version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "版本不存在")
    if version.submission_id != submission.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该版本不属于此提交")

    comp = await _competition_of_submission(session, submission)
    try:
        record = await ai.assess_version(session, target_version_id, comp, admin)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    return _review_out(record)


# ───────────────────── 3. 赛事全部预评级 ─────────────────────
@router.get(
    "/competitions/{competition_id}/ai/assessments",
    response_model=list[AIReviewOut],
    summary="赛事 AI 预评级留档（管理员）",
)
async def list_assessments(
    competition_id: str,
    status: AIReviewStatus | None = None,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(_admin),
) -> list[AIReviewOut]:
    await _get_competition_or_404(session, competition_id)

    stmt = (
        select(AIReviewRecord)
        .join(SubmissionVersion, AIReviewRecord.version_id == SubmissionVersion.id)
        .join(Submission, SubmissionVersion.submission_id == Submission.id)
        .join(Enrollment, Submission.enrollment_id == Enrollment.id)
        .where(Enrollment.competition_id == competition_id)
    )
    if status is not None:
        stmt = stmt.where(AIReviewRecord.status == status.value)

    rows = (await session.execute(stmt.order_by(AIReviewRecord.created_at.desc()))).scalars().all()
    # 关联查询可能产生重复行，按记录主键去重
    seen: set[str] = set()
    out: list[AIReviewOut] = []
    for row in rows:
        if row.id in seen:
            continue
        seen.add(row.id)
        out.append(_review_out(row))
    return out


# ───────────────────── 4. 专家端风险标记（防锚定）─────────────────────
@router.get(
    "/review-tasks/{task_id}/ai-risk-flags",
    response_model=ReviewRiskFlagsOut,
    summary="评审任务 AI 风险标记（不含分数）",
)
async def review_risk_flags(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(_judge),
) -> ReviewRiskFlagsOut:
    task = await session.get(ReviewTask, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if task.reviewer_id != user.id and user.role != Role.ADMIN.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "不是你的评审任务")

    record: AIReviewRecord | None = None
    submission = await session.get(Submission, task.submission_id)
    if submission is not None and submission.current_version_id:
        record = (
            await session.execute(
                select(AIReviewRecord)
                .where(AIReviewRecord.version_id == submission.current_version_id)
                .order_by(AIReviewRecord.created_at.desc())
            )
        ).scalars().first()

    if record is None:
        return ReviewRiskFlagsOut(
            task_id=task.id,
            status="NONE",
            risk_flags=[],
            notice="无 AI 参考，按人工评审流程进行",
        )

    return ReviewRiskFlagsOut(
        task_id=task.id,
        status=record.status,
        risk_flags=_parse_risk_flags(record.risk_flags_json),
        notice="以下为 AI 标记的风险信号，仅供参考；AI 不参与成绩评定",
    )


# ───────────────────── 5. 触发确定性分流 ─────────────────────
@router.post(
    "/competitions/{competition_id}/ai/escalations/evaluate",
    response_model=list[EscalationOut],
    summary="运行确定性复审规则（管理员）",
)
async def evaluate_competition_escalations(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> list[EscalationOut]:
    comp = await _get_competition_or_404(session, competition_id)
    created = await ai.evaluate_escalations(session, comp, admin)
    return [_escalation_out(row) for row in created]


# ───────────────────── 6. 复审触发留档 ─────────────────────
@router.get(
    "/competitions/{competition_id}/ai/escalations",
    response_model=list[EscalationOut],
    summary="赛事复审触发记录（管理员）",
)
async def list_escalations(
    competition_id: str,
    status: EscalationStatus | None = None,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(_admin),
) -> list[EscalationOut]:
    await _get_competition_or_404(session, competition_id)

    stmt = select(ReviewEscalation).where(ReviewEscalation.competition_id == competition_id)
    if status is not None:
        stmt = stmt.where(ReviewEscalation.status == status.value)
    rows = (await session.execute(stmt.order_by(ReviewEscalation.created_at.desc()))).scalars().all()
    return [_escalation_out(row) for row in rows]


# ───────────────────── 7. 处理复审触发 ─────────────────────
@router.patch(
    "/ai/escalations/{escalation_id}",
    response_model=EscalationOut,
    summary="处理复审触发记录（管理员）",
)
async def handle_escalation(
    escalation_id: str,
    payload: EscalationHandleIn,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> EscalationOut:
    row = await session.get(ReviewEscalation, escalation_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "复审触发记录不存在")
    if row.status != EscalationStatus.OPEN.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "该复审触发记录已处理")

    before = {"status": row.status, "note": row.note, "handled_by": row.handled_by}
    row.status = payload.status
    row.note = payload.note
    row.handled_by = admin.id
    row.handled_at = datetime.now(UTC)
    await audit.record(
        session,
        action=AuditAction.ESCALATE,
        object_type="ReviewEscalation",
        object_id=row.id,
        actor=admin,
        before=before,
        after={"status": row.status, "note": row.note, "handled_by": admin.id},
        reason="管理员处理复审触发记录",
    )
    await session.flush()
    return _escalation_out(row)
