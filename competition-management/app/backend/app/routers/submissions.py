"""路由：作品提交与版本管理（FR-009～FR-011）。"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.constants import AuditAction, Role, SubmissionStatus, TeamMemberRole
from app.core.deps import get_current_user
from app.db.session import get_session
from app.models import (
    BlobObject,
    Competition,
    Enrollment,
    Submission,
    SubmissionVersion,
    Team,
    TeamMember,
    User,
)
from app.schemas import SubmissionOut, VersionOut
from app.services import audit
from app.services.rules import ensure_submittable, ensure_version_before_deadline, is_submission_open
from app.services.storage import get_storage

router = APIRouter(prefix="/submissions", tags=["作品提交"])


async def _load_submission(session: AsyncSession, submission_id: str) -> Submission:
    stmt = (
        select(Submission)
        .where(Submission.id == submission_id)
        .options(selectinload(Submission.versions))
    )
    sub = (await session.execute(stmt)).scalar_one_or_none()
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "提交记录不存在")
    return sub


async def _ensure_allowed(session: AsyncSession, submission: Submission, user: User) -> None:
    """只有队伍成员（含队长）或管理员能操作提交。"""
    if user.role == Role.ADMIN.value:
        return
    enr = await session.get(Enrollment, submission.enrollment_id)
    assert enr is not None
    member = (
        await session.execute(
            select(TeamMember).where(TeamMember.team_id == enr.team_id, TeamMember.user_id == user.id)
        )
    ).scalar_one_or_none()
    if member is None or member.role_in_team == TeamMemberRole.ADVISOR.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只有队伍成员可以操作该提交")


# ───────────────────── 创建 / 读取 ─────────────────────
@router.post("/by-enrollment/{enrollment_id}", response_model=SubmissionOut, status_code=201,
             summary="为报名创建提交记录")
async def create_submission(
    enrollment_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SubmissionOut:
    enr = await session.get(Enrollment, enrollment_id)
    if enr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "报名记录不存在")
    if enr.status != "APPROVED" and user.role != Role.ADMIN.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "报名尚未通过资格审核")

    exists = (
        await session.execute(select(Submission).where(Submission.enrollment_id == enrollment_id))
    ).scalar_one_or_none()
    if exists:
        return SubmissionOut.model_validate(await _load_submission(session, exists.id))

    same_team = (
        await session.execute(
            select(TeamMember).where(TeamMember.team_id == enr.team_id, TeamMember.user_id == user.id)
        )
    ).scalar_one_or_none()
    if same_team is None and user.role != Role.ADMIN.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "你不是该队伍成员")

    sub = Submission(enrollment_id=enrollment_id, status=SubmissionStatus.DRAFT.value)
    session.add(sub)
    await session.flush()
    return SubmissionOut.model_validate(await _load_submission(session, sub.id))


@router.get("/{submission_id}", response_model=SubmissionOut, summary="提交详情与版本列表")
async def get_submission(
    submission_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SubmissionOut:
    sub = await _load_submission(session, submission_id)
    await _ensure_allowed(session, sub, user)
    return SubmissionOut.model_validate(sub)


# ───────────────────── 上传新版本 ─────────────────────
@router.post("/{submission_id}/versions", response_model=VersionOut, status_code=201,
             summary="上传新版本（FR-009/FR-010）")
async def upload_version(
    submission_id: str,
    file: UploadFile = File(...),
    note: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> VersionOut:
    sub = await _load_submission(session, submission_id)
    await _ensure_allowed(session, sub, user)

    enr = await session.get(Enrollment, sub.enrollment_id)
    assert enr is not None
    comp = await session.get(Competition, enr.competition_id)
    assert comp is not None

    ensure_version_before_deadline(comp)

    name = file.filename or "unnamed"
    ext = Path(name).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"不支持的文件类型 {ext}，允许：{', '.join(sorted(settings.allowed_extensions))}",
        )

    storage = get_storage()
    storage_key = f"{uuid.uuid4().hex}{ext}"

    # 流式落盘：边写边算 md5，内存占用恒定为 1MB，超限立即中断并清理半成品。
    await file.seek(0)
    try:
        md5, size = storage.put_fileobj(
            storage_key, file.file, max_bytes=settings.max_upload_bytes
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"文件超过上限 {settings.max_upload_bytes // (1024 * 1024)} MB",
        ) from exc

    if size == 0:
        storage.delete(storage_key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件为空")

    # 秒传：同 md5+size 的 blob 已存在则复用，ref_count +1
    blob = (
        await session.execute(
            select(BlobObject).where(BlobObject.md5 == md5, BlobObject.size_bytes == size)
        )
    ).scalar_one_or_none()

    if blob is None:
        blob = BlobObject(
            md5=md5,
            size_bytes=size,
            storage_key=storage_key,
            original_name=name,
            mime_type=file.content_type,
            ref_count=1,
        )
        session.add(blob)
        await session.flush()
    else:
        blob.ref_count += 1
        storage.delete(storage_key)  # 内容重复，刚写的那份丢掉

    next_no = (
        await session.execute(
            select(func.coalesce(func.max(SubmissionVersion.version_no), 0)).where(
                SubmissionVersion.submission_id == submission_id
            )
        )
    ).scalar_one() + 1

    version = SubmissionVersion(
        submission_id=submission_id,
        version_no=next_no,
        blob_id=blob.id,
        note=note,
        uploaded_by=user.id,
    )
    session.add(version)
    await session.flush()

    sub.current_version_id = version.id

    await audit.record(
        session,
        action=AuditAction.CREATE,
        object_type="SubmissionVersion",
        object_id=version.id,
        actor=user,
        after={"submission_id": submission_id, "version_no": next_no, "md5": md5, "size": size},
    )
    return VersionOut.model_validate(version)


# ───────────────────── 提交 / 撤回 ─────────────────────
@router.post("/{submission_id}/submit", response_model=SubmissionOut, summary="正式提交（FR-011）")
async def submit(
    submission_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SubmissionOut:
    sub = await _load_submission(session, submission_id)
    await _ensure_allowed(session, sub, user)

    enr = await session.get(Enrollment, sub.enrollment_id)
    assert enr is not None
    comp = await session.get(Competition, enr.competition_id)
    assert comp is not None

    if not is_submission_open(comp):
        raise HTTPException(status.HTTP_409_CONFLICT, "当前不在提交时间窗内")
    if not sub.current_version_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "尚未上传任何版本，无法提交")
    ensure_submittable(comp, sub)

    sub.status = SubmissionStatus.SUBMITTED.value
    sub.submitted_at = func.now()

    await audit.record(
        session,
        action=AuditAction.SUBMIT,
        object_type="Submission",
        object_id=sub.id,
        actor=user,
        after={"version_id": sub.current_version_id},
    )
    await session.flush()
    return SubmissionOut.model_validate(await _load_submission(session, submission_id))


@router.post("/{submission_id}/withdraw", response_model=SubmissionOut, summary="撤回提交")
async def withdraw(
    submission_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SubmissionOut:
    sub = await _load_submission(session, submission_id)
    await _ensure_allowed(session, sub, user)

    if sub.status != SubmissionStatus.SUBMITTED.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "只有已提交状态可以撤回")

    enr = await session.get(Enrollment, sub.enrollment_id)
    assert enr is not None
    comp = await session.get(Competition, enr.competition_id)
    assert comp is not None
    if not is_submission_open(comp):
        raise HTTPException(status.HTTP_409_CONFLICT, "已过截止时间，无法撤回")

    sub.status = SubmissionStatus.WITHDRAWN.value
    await audit.record(
        session,
        action=AuditAction.UPDATE,
        object_type="Submission",
        object_id=sub.id,
        actor=user,
        after={"status": sub.status},
        reason="用户撤回",
    )
    await session.flush()
    return SubmissionOut.model_validate(await _load_submission(session, submission_id))
