"""路由：数据导出与赛事归档（FR-025）。

导出内容即时生成并存进 ExportJob.content，列表/摘要接口不回吐完整内容；
归档只记录快照 key 并把赛事推进到 ARCHIVED，本模块不提供任何修改归档赛事数据的接口。
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    FORCE_ARCHIVE_SOURCES,
    AuditAction,
    CompetitionState,
    ExportStatus,
    Role,
)
from app.core.deps import get_current_user, require_roles
from app.db.session import get_session
from app.models import (
    ArchiveRecord,
    AuditLog,
    Competition,
    CompetitionResult,
    Enrollment,
    ExportJob,
    ReviewTask,
    Submission,
    Team,
    User,
)
from app.services import audit

router = APIRouter(tags=["导出与归档"])

_admin = require_roles(Role.ADMIN)

ALLOWED_DATA_KINDS = frozenset(
    {"ENROLLMENTS", "TEAMS", "SUBMISSIONS", "REVIEWS", "RESULTS", "AUDIT"}
)
ALLOWED_EXPORT_FORMATS = frozenset({"CSV", "JSON"})

# 每种数据的列顺序固定，空结果集也能产出带表头的 CSV。
FIELDS_BY_KIND: dict[str, tuple[str, ...]] = {
    "ENROLLMENTS": (
        "id",
        "competition_id",
        "team_id",
        "status",
        "review_comment",
        "reviewed_by",
        "created_at",
    ),
    "TEAMS": ("id", "competition_id", "name", "school", "invite_code", "created_at"),
    "SUBMISSIONS": (
        "id",
        "enrollment_id",
        "status",
        "current_version_id",
        "submitted_at",
        "created_at",
    ),
    "REVIEWS": (
        "id",
        "competition_id",
        "submission_id",
        "reviewer_id",
        "status",
        "material_ref",
        "created_at",
    ),
    "RESULTS": (
        "id",
        "competition_id",
        "team_id",
        "team_name",
        "final_score",
        "rank",
        "award",
        "status",
        "review_count",
        "published_at",
        "created_at",
    ),
    "AUDIT": (
        "id",
        "action",
        "object_type",
        "object_id",
        "actor_email",
        "reason",
        "created_at",
    ),
}


# ─────────────── 本地 schema ───────────────
class ExportCreate(BaseModel):
    data_kind: str
    export_format: str = "CSV"


class ExportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    competition_id: str
    data_kind: str
    export_format: str
    row_count: int
    status: str
    created_at: datetime


class ArchiveCreate(BaseModel):
    note: str | None = None


class ArchiveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    competition_id: str
    snapshot_key: str | None
    archived_by: str | None
    note: str | None
    created_at: datetime


# ─────────────── 内部工具 ───────────────
async def _get_competition(session: AsyncSession, competition_id: str) -> Competition:
    comp = await session.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "赛事不存在")
    return comp


def _project(obj: object, fields: tuple[str, ...]) -> dict[str, object]:
    return {name: getattr(obj, name) for name in fields}


async def _collect_rows(
    session: AsyncSession, competition_id: str, data_kind: str
) -> list[dict[str, object]]:
    """按数据类型抓取赛事数据，字段顺序与 FIELDS_BY_KIND 对齐。"""
    fields = FIELDS_BY_KIND[data_kind]

    if data_kind == "ENROLLMENTS":
        stmt = (
            select(Enrollment)
            .where(Enrollment.competition_id == competition_id)
            .order_by(Enrollment.created_at)
        )
        rows = (await session.execute(stmt)).scalars().all()
    elif data_kind == "TEAMS":
        stmt = (
            select(Team)
            .where(Team.competition_id == competition_id)
            .order_by(Team.created_at)
        )
        rows = (await session.execute(stmt)).scalars().all()
    elif data_kind == "SUBMISSIONS":
        stmt = (
            select(Submission)
            .join(Enrollment, Submission.enrollment_id == Enrollment.id)
            .where(Enrollment.competition_id == competition_id)
            .order_by(Submission.created_at)
        )
        rows = (await session.execute(stmt)).scalars().all()
    elif data_kind == "REVIEWS":
        stmt = (
            select(ReviewTask)
            .where(ReviewTask.competition_id == competition_id)
            .order_by(ReviewTask.created_at)
        )
        rows = (await session.execute(stmt)).scalars().all()
    elif data_kind == "RESULTS":
        stmt = (
            select(CompetitionResult)
            .where(CompetitionResult.competition_id == competition_id)
            .order_by(CompetitionResult.rank)
        )
        rows = (await session.execute(stmt)).scalars().all()
    else:  # AUDIT
        stmt = (
            select(AuditLog)
            .where(AuditLog.object_id == competition_id)
            .order_by(AuditLog.created_at)
        )
        rows = (await session.execute(stmt)).scalars().all()

    return [_project(row, fields) for row in rows]


def _render(rows: list[dict[str, object]], fields: tuple[str, ...], export_format: str) -> str:
    if export_format == "JSON":
        return json.dumps(rows, ensure_ascii=False, default=str)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(fields), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def _summary(job: ExportJob) -> ExportSummary:
    return ExportSummary.model_validate(job)


# ─────────────── 导出 ───────────────
@router.post(
    "/competitions/{competition_id}/exports",
    response_model=ExportSummary,
    summary="生成数据导出（FR-025）",
)
async def create_export(
    competition_id: str,
    payload: ExportCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> ExportSummary:
    await _get_competition(session, competition_id)

    if payload.data_kind not in ALLOWED_DATA_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"不支持的数据类型：{payload.data_kind}")
    if payload.export_format not in ALLOWED_EXPORT_FORMATS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"不支持的导出格式：{payload.export_format}")

    fields = FIELDS_BY_KIND[payload.data_kind]
    rows = await _collect_rows(session, competition_id, payload.data_kind)
    job = ExportJob(
        competition_id=competition_id,
        data_kind=payload.data_kind,
        export_format=payload.export_format,
        status=ExportStatus.COMPLETED.value,
        row_count=len(rows),
        content=_render(rows, fields, payload.export_format),
        requested_by=admin.id,
    )
    session.add(job)
    await session.flush()

    await audit.record(
        session,
        action=AuditAction.EXPORT,
        object_type="ExportJob",
        object_id=job.id,
        actor=admin,
        after={
            "competition_id": competition_id,
            "data_kind": payload.data_kind,
            "export_format": payload.export_format,
            "row_count": job.row_count,
        },
    )
    return _summary(job)


@router.get(
    "/competitions/{competition_id}/exports",
    response_model=list[ExportSummary],
    summary="赛事导出任务列表（FR-025）",
)
async def list_exports(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(_admin),
) -> list[ExportSummary]:
    await _get_competition(session, competition_id)
    stmt = (
        select(ExportJob)
        .where(ExportJob.competition_id == competition_id)
        .order_by(ExportJob.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_summary(job) for job in rows]


@router.get("/exports/{export_id}/content", summary="下载导出内容（FR-025）")
async def download_export(
    export_id: str,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(_admin),
) -> PlainTextResponse:
    job = await session.get(ExportJob, export_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "导出任务不存在")
    media_type = (
        "text/csv; charset=utf-8" if job.export_format == "CSV" else "application/json"
    )
    return PlainTextResponse(job.content, media_type=media_type)


# ─────────────── 归档 ───────────────
@router.post(
    "/competitions/{competition_id}/archive",
    response_model=ArchiveOut,
    summary="归档赛事（FR-025）",
)
async def archive_competition(
    competition_id: str,
    payload: ArchiveCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(_admin),
) -> ArchiveOut:
    comp = await _get_competition(session, competition_id)
    current = CompetitionState(comp.state)

    is_normal = current is CompetitionState.APPEAL
    is_forced = current in FORCE_ARCHIVE_SOURCES
    if not (is_normal or is_forced):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"当前状态 {current.value} 不允许归档，请先将赛事推进到申诉阶段或符合强制归档条件",
        )

    # 强制归档属于高风险操作，必须留下可追溯的原因。
    if is_forced and (payload.note is None or len(payload.note.strip()) < 5):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "强制归档必须填写至少 5 个字的原因说明")

    before_state = current.value
    record = ArchiveRecord(
        competition_id=competition_id,
        snapshot_key=f"archive/{competition_id}/{uuid4().hex}.json",
        archived_by=admin.id,
        note=payload.note,
    )
    session.add(record)
    comp.state = CompetitionState.ARCHIVED.value

    await audit.record(
        session,
        action=AuditAction.ARCHIVE,
        object_type="Competition",
        object_id=competition_id,
        actor=admin,
        before={"state": before_state},
        after={"state": CompetitionState.ARCHIVED.value, "snapshot_key": record.snapshot_key},
        reason=payload.note,
    )
    await session.flush()
    return ArchiveOut.model_validate(record)


@router.get(
    "/competitions/{competition_id}/archive",
    response_model=list[ArchiveOut],
    summary="赛事归档记录（FR-025）",
)
async def list_archives(
    competition_id: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> list[ArchiveOut]:
    stmt = (
        select(ArchiveRecord)
        .where(ArchiveRecord.competition_id == competition_id)
        .order_by(ArchiveRecord.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [ArchiveOut.model_validate(row) for row in rows]
