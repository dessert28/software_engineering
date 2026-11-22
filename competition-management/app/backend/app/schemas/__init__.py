"""Pydantic v2 请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.constants import (
    CompetitionState,
    EnrollmentStatus,
    ReviewTaskStatus,
    Role,
    SubmissionStatus,
    TeamMemberRole,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ───────────────────────── 认证 ─────────────────────────
class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)


class RegisterRequest(BaseModel):
    """学生自助注册：只允许 CAPTAIN / MEMBER，特权角色由管理员创建。"""

    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=2, max_length=120)
    school: str | None = Field(default=None, max_length=200)
    role: Literal["CAPTAIN", "MEMBER"] = "CAPTAIN"

    @field_validator("email")
    @classmethod
    def _email_shape(cls, v: str) -> str:
        email = v.strip().lower()
        local, sep, domain = email.partition("@")
        if not sep or not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("邮箱格式不正确")
        return email

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return v.strip()


class UserOut(ORMModel):
    id: str
    email: str
    name: str
    role: Role
    school: str | None = None
    can_review: bool = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ───────────────────────── 赛事 ─────────────────────────
class CompetitionCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    edition: str | None = Field(default=None, max_length=50)
    organizer: str | None = Field(default=None, max_length=200)
    description: str | None = None
    min_team_size: int = Field(default=1, ge=1, le=10)
    max_team_size: int = Field(default=3, ge=1, le=10)
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    submission_opens_at: datetime | None = None
    submission_closes_at: datetime | None = None
    review_closes_at: datetime | None = None
    result_publishes_at: datetime | None = None

    @field_validator("max_team_size")
    @classmethod
    def _size_order(cls, v: int, info) -> int:
        low = info.data.get("min_team_size", 1)
        if v < low:
            raise ValueError("max_team_size 不能小于 min_team_size")
        return v

    @field_validator("registration_closes_at")
    @classmethod
    def _reg_order(cls, v: datetime | None, info):
        opens = info.data.get("registration_opens_at")
        if v and opens and v <= opens:
            raise ValueError("报名截止时间必须晚于报名开始时间")
        return v

    @field_validator("submission_closes_at")
    @classmethod
    def _sub_order(cls, v: datetime | None, info):
        opens = info.data.get("submission_opens_at")
        if v and opens and v <= opens:
            raise ValueError("提交截止时间必须晚于提交开始时间")
        return v


class CompetitionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    edition: str | None = None
    organizer: str | None = None
    description: str | None = None
    min_team_size: int | None = Field(default=None, ge=1, le=10)
    max_team_size: int | None = Field(default=None, ge=1, le=10)
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    submission_opens_at: datetime | None = None
    submission_closes_at: datetime | None = None
    review_closes_at: datetime | None = None
    result_publishes_at: datetime | None = None


class CompetitionOut(ORMModel):
    id: str
    title: str
    edition: str | None
    organizer: str | None
    description: str | None
    state: CompetitionState
    min_team_size: int
    max_team_size: int
    registration_opens_at: datetime | None
    registration_closes_at: datetime | None
    submission_opens_at: datetime | None
    submission_closes_at: datetime | None
    review_closes_at: datetime | None
    result_publishes_at: datetime | None
    created_at: datetime


class TransitionRequest(BaseModel):
    target: CompetitionState
    reason: str | None = Field(default=None, max_length=500)


class TransitionOut(BaseModel):
    competition: CompetitionOut
    previous_state: CompetitionState
    allowed_next: list[CompetitionState]


# ───────────────────────── 公告 / 题目 ─────────────────────────
class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=1)
    visible_to: str = "ALL"


class AnnouncementOut(ORMModel):
    id: str
    competition_id: str
    title: str
    body: str
    visible_to: str
    is_withdrawn: bool
    created_at: datetime


class ProblemCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=2, max_length=200)
    statement: str = ""
    is_published: bool = False


class ProblemOut(ORMModel):
    id: str
    competition_id: str
    code: str
    title: str
    statement: str
    is_published: bool


# ───────────────────────── 队伍 / 报名 ─────────────────────────
class TeamCreate(BaseModel):
    competition_id: str
    name: str = Field(min_length=2, max_length=120)
    school: str | None = Field(default=None, max_length=200)


class TeamMemberAdd(BaseModel):
    user_id: str | None = None
    email: str | None = None
    name: str | None = None
    role_in_team: TeamMemberRole = TeamMemberRole.MEMBER
    contact: str | None = None


class TeamMemberOut(ORMModel):
    id: str
    user_id: str
    role_in_team: TeamMemberRole
    contact: str | None


class TeamOut(ORMModel):
    id: str
    name: str
    school: str | None
    competition_id: str
    invite_code: str
    members: list[TeamMemberOut] = []


class EnrollmentCreate(BaseModel):
    competition_id: str
    team_id: str


class EnrollmentReview(BaseModel):
    status: EnrollmentStatus
    comment: str | None = Field(default=None, max_length=1000)


class EnrollmentOut(ORMModel):
    id: str
    competition_id: str
    team_id: str
    status: EnrollmentStatus
    review_comment: str | None
    created_at: datetime


# ───────────────────────── 提交 ─────────────────────────
class VersionCreate(BaseModel):
    note: str | None = Field(default=None, max_length=500)
    # 可选：直接登记已上传 blob 的 md5（秒传场景）
    md5: str | None = Field(default=None, min_length=32, max_length=32)
    size_bytes: int | None = Field(default=None, ge=0)


class VersionOut(ORMModel):
    id: str
    submission_id: str
    version_no: int
    blob_id: str
    note: str | None
    created_at: datetime


class SubmissionOut(ORMModel):
    id: str
    enrollment_id: str
    status: SubmissionStatus
    current_version_id: str | None
    submitted_at: datetime | None
    versions: list[VersionOut] = []


# ───────────────────────── 评审 ─────────────────────────
class JudgeCreate(BaseModel):
    email: str
    name: str
    password: str = Field(min_length=6, max_length=128)
    school: str | None = None
    expertise: str | None = None


class ReviewTaskCreate(BaseModel):
    competition_id: str
    submission_id: str
    reviewer_id: str
    due_at: datetime | None = None


class ReviewTaskOut(ORMModel):
    id: str
    competition_id: str
    submission_id: str
    reviewer_id: str
    status: ReviewTaskStatus
    due_at: datetime | None
    material_ref: str


class AnonymousMaterial(BaseModel):
    """匿名材料视图：不含队伍、学校、指导教师、队员姓名。"""

    task_id: str
    competition_title: str
    problem_code: str
    version_no: int
    file_name: str | None
    file_size: int | None
    note: str | None
    rubric: list[dict[str, Any]]


class ScoreSubmit(BaseModel):
    dimension: dict[str, float]
    comment: str | None = Field(default=None, max_length=4000)

    @field_validator("dimension")
    @classmethod
    def _non_empty(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("维度分不能为空")
        for k, val in v.items():
            if not (0 <= val <= 100):
                raise ValueError(f"维度 {k} 的分数必须在 0～100 之间")
        return v


class ScoreOut(ORMModel):
    id: str
    task_id: str
    reviewer_id: str
    dimension_json: str
    total_score: float
    comment: str | None
    authority: str


class ReviewProgress(BaseModel):
    competition_id: str
    total_tasks: int
    submitted: int
    in_progress: int
    assigned: int
    overdue: int
    completion_rate: float


# ───────────────────────── 结果 ─────────────────────────
class ResultOut(ORMModel):
    id: str
    competition_id: str
    team_id: str
    team_name: str
    final_score: float
    rank: int | None
    award: str | None
    status: str
    review_count: int


class CalculateResponse(BaseModel):
    competition_id: str
    computed: int
    skipped: list[str] = []
    results: list[ResultOut] = []


# ───────────────────────── 审计 ─────────────────────────
class AuditOut(ORMModel):
    id: str
    action: str
    object_type: str
    object_id: str | None
    actor_email: str | None
    reason: str | None
    created_at: datetime
