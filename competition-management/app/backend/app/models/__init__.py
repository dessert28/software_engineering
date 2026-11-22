"""SQLAlchemy 模型：17 个业务对象，对应 experiments/exp2 的 CRC 卡片。

命名与 exp2/business_objects.md 一致，便于把设计文档与代码对照阅读。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    AIReviewStatus,
    AppealStatus,
    CompetitionState,
    EnrollmentStatus,
    EscalationStatus,
    ExportStatus,
    IssueStatus,
    NotificationStatus,
    RecheckStatus,
    ResultStatus,
    ReviewExceptionStatus,
    ReviewTaskStatus,
    RevisionStatus,
    ScoreAuthority,
    SubmissionStatus,
    TeamMemberRole,
)
from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


# ─────────────────────────── 1. User ───────────────────────────
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    school: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # 评审专家专用
    expertise: Mapped[str | None] = mapped_column(String(400))
    can_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    memberships: Mapped[list["TeamMember"]] = relationship(back_populates="user")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="actor")


# ──────────────────── 2. Competition ────────────────────
class Competition(Base, TimestampMixin):
    __tablename__ = "competitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    edition: Mapped[str | None] = mapped_column(String(50))
    organizer: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(
        String(40), default=CompetitionState.DRAFT.value, nullable=False, index=True
    )

    # 时间节点（FR-003）：ISO 字符串存库，读取时转 datetime 由 schema 负责
    registration_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submission_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submission_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_publishes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    max_team_size: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    min_team_size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    rule_profile_id: Mapped[str | None] = mapped_column(ForeignKey("rule_profiles.id"))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    rule_profile: Mapped["RuleProfile | None"] = relationship(back_populates="competitions")
    announcements: Mapped[list["Announcement"]] = relationship(
        back_populates="competition", cascade="all, delete-orphan"
    )
    problems: Mapped[list["ProblemSet"]] = relationship(
        back_populates="competition", cascade="all, delete-orphan"
    )
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="competition")
    results: Mapped[list["CompetitionResult"]] = relationship(back_populates="competition")


# ─────────────── 3. RuleProfile ───────────────
class RuleProfile(Base, TimestampMixin):
    """赛事规则快照：评分细则与汇总规则版本化，改规则不影响历史赛事。"""

    __tablename__ = "rule_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # JSON 字符串：{"items":[{"key":"modeling","weight":40},...],"trim_high":1,"trim_low":1}
    rubric_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # 汇总策略：MEAN | TRIMMED_MEAN | MEDIAN
    aggregation: Mapped[str] = mapped_column(String(20), default="MEAN", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    competitions: Mapped[list["Competition"]] = relationship(back_populates="rule_profile")

    __table_args__ = (UniqueConstraint("name", "version", name="uq_rule_profile_name_version"),)


# ─────────────── 4. Announcement ───────────────
class Announcement(Base, TimestampMixin):
    __tablename__ = "announcements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    competition_id: Mapped[str] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    visible_to: Mapped[str] = mapped_column(String(40), default="ALL", nullable=False)
    is_withdrawn: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    competition: Mapped["Competition"] = relationship(back_populates="announcements")


# ─────────────── 5. ProblemSet ───────────────
class ProblemSet(Base, TimestampMixin):
    __tablename__ = "problem_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    competition_id: Mapped[str] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    competition: Mapped["Competition"] = relationship(back_populates="problems")

    __table_args__ = (
        UniqueConstraint("competition_id", "code", name="uq_problem_competition_code"),
    )


# ─────────────── 6. Team ───────────────
class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    school: Mapped[str | None] = mapped_column(String(200))
    # 冗余存放所属赛事，用于唯一约束 (competition_id, team_name)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id"), nullable=False, index=True)
    invite_code: Mapped[str] = mapped_column(String(16), default=lambda: _uuid()[:8], nullable=False)

    members: Mapped[list["TeamMember"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="team")

    # 六条强制唯一约束之一
    __table_args__ = (
        UniqueConstraint("competition_id", "name", name="uq_team_competition_name"),
    )


# ─────────────── 7. TeamMember（Team 与 User 的中间实体）───────────────
class TeamMember(Base, TimestampMixin):
    __tablename__ = "team_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role_in_team: Mapped[str] = mapped_column(
        String(20), default=TeamMemberRole.MEMBER.value, nullable=False
    )
    contact: Mapped[str | None] = mapped_column(String(120))

    team: Mapped["Team"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="memberships")

    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)


# ─────────────── 8. Enrollment ───────────────
class Enrollment(Base, TimestampMixin):
    __tablename__ = "enrollments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id"), nullable=False, index=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=EnrollmentStatus.PENDING.value, nullable=False, index=True
    )
    review_comment: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    competition: Mapped["Competition"] = relationship(back_populates="enrollments")
    team: Mapped["Team"] = relationship(back_populates="enrollments")
    submission: Mapped["Submission | None"] = relationship(
        back_populates="enrollment", uselist=False
    )

    __table_args__ = (
        UniqueConstraint("competition_id", "team_id", name="uq_enrollment_competition_team"),
    )


# ─────────────── 9. SubmissionAsset ───────────────
class SubmissionAsset(Base, TimestampMixin):
    """提交物：一个报名对应一个作品载体，下挂多个版本。"""

    __tablename__ = "submission_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    enrollment_id: Mapped[str] = mapped_column(ForeignKey("enrollments.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    current_version_id: Mapped[str | None] = mapped_column(String(36))


class Submission(Base, TimestampMixin):
    """报名对应的提交记录：承载状态与锁定信息。"""

    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    enrollment_id: Mapped[str] = mapped_column(
        ForeignKey("enrollments.id"), nullable=False, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=SubmissionStatus.DRAFT.value, nullable=False, index=True
    )
    current_version_id: Mapped[str | None] = mapped_column(String(36))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    enrollment: Mapped["Enrollment"] = relationship(back_populates="submission")
    versions: Mapped[list["SubmissionVersion"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", order_by="SubmissionVersion.version_no"
    )


# ─────────────── 10. BlobObject（内容寻址存储）───────────────
class BlobObject(Base, TimestampMixin):
    """按 (md5, size) 内容寻址。相同内容只存一份，ref_count 归零后可清理。"""

    __tablename__ = "blob_objects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    md5: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(400), nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    ref_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 六条强制唯一约束之一：秒传基础
    __table_args__ = (UniqueConstraint("md5", "size_bytes", name="uq_blob_md5_size"),)


# ─────────────── 11. SubmissionVersion ───────────────
class SubmissionVersion(Base, TimestampMixin):
    __tablename__ = "submission_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    blob_id: Mapped[str] = mapped_column(ForeignKey("blob_objects.id"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    submission: Mapped["Submission"] = relationship(back_populates="versions")
    blob: Mapped["BlobObject"] = relationship()

    # 六条强制唯一约束之一
    __table_args__ = (
        UniqueConstraint("submission_id", "version_no", name="uq_version_submission_no"),
    )


# ─────────────── 12. RubricProfile ───────────────
class RubricProfile(Base, TimestampMixin):
    """评分细则模板。初版与 RuleProfile 并存：RuleProfile 供赛事引用，RubricProfile 供任务快照。"""

    __tablename__ = "rubric_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    items_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    total_score: Mapped[int] = mapped_column(Integer, default=100, nullable=False)


# ─────────────── 13. ReviewTask ───────────────
class ReviewTask(Base, TimestampMixin):
    __tablename__ = "review_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id"), nullable=False, index=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), nullable=False, index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    rubric_id: Mapped[str | None] = mapped_column(ForeignKey("rubric_profiles.id"))
    status: Mapped[str] = mapped_column(
        String(20), default=ReviewTaskStatus.ASSIGNED.value, nullable=False, index=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 匿名材料标识：专家只见此串，与真实 submission 的映射仅管理员可读
    material_ref: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    reviewer: Mapped["User"] = relationship()
    scores: Mapped[list["ScoreRecord"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )

    # 六条强制唯一约束之一
    __table_args__ = (
        UniqueConstraint("submission_id", "reviewer_id", name="uq_task_submission_reviewer"),
    )


# ─────────────── 14. ScoreRecord ───────────────
class ScoreRecord(Base, TimestampMixin):
    __tablename__ = "score_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("review_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    # 维度分：JSON 字符串 {"modeling":88,"solving":85,"writing":90}
    dimension_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    total_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    comment: Mapped[str | None] = mapped_column(Text)
    authority: Mapped[str] = mapped_column(
        String(20), default=ScoreAuthority.HUMAN.value, nullable=False
    )
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    task: Mapped["ReviewTask"] = relationship(back_populates="scores")


# ─────────────── 15. CompetitionResult ───────────────
class CompetitionResult(Base, TimestampMixin):
    __tablename__ = "competition_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id"), nullable=False, index=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    team_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    final_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    rank: Mapped[int | None] = mapped_column(Integer)
    award: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(
        String(20), default=ResultStatus.DRAFT.value, nullable=False, index=True
    )
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    competition: Mapped["Competition"] = relationship(back_populates="results")

    __table_args__ = (
        UniqueConstraint("competition_id", "team_id", name="uq_result_competition_team"),
    )


# ─────────────── 16. Appeal ───────────────
class Appeal(Base, TimestampMixin):
    __tablename__ = "appeals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    appeal_no: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, default=lambda: f"AP-{_uuid()[:8].upper()}"
    )
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id"), nullable=False, index=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    submitted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=AppealStatus.OPEN.value, nullable=False, index=True
    )
    resolution: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(String(20))
    handled_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("appeal_no", name="uq_appeal_no"),)


# ─────────────── 17. AuditLog（只 INSERT）───────────────
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    actor_email: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    object_id: Mapped[str | None] = mapped_column(String(36), index=True)
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False, index=True
    )

    actor: Mapped["User | None"] = relationship(back_populates="audit_logs")


# ─────────────── 附加：ArchiveRecord ───────────────
class ArchiveRecord(Base, TimestampMixin):
    __tablename__ = "archive_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id"), nullable=False, index=True)
    snapshot_key: Mapped[str | None] = mapped_column(String(400))
    archived_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)


# ─────────────── 附加：CollaborationNote ───────────────
class CollaborationNote(Base, TimestampMixin):
    """队内协作备注。实验二遗留问题：边界定为「队内」，与管理员沟通不进此表。"""

    __tablename__ = "collaboration_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text, nullable=False)


# ─────────────── AIReviewRecord（AI 预评级留档）───────────────
class AIReviewRecord(Base, TimestampMixin):
    """AI 预评级留档。authority 恒为 ADVISORY，永不进入成绩加权。

    六条强制唯一约束之一：(version_id, model_id, prompt_version, input_hash)
    保证同一输入同一模型同一提示词只跑一次，重跑为幂等更新。
    """

    __tablename__ = "ai_review_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("submission_versions.id"), nullable=False, index=True
    )
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    suggested_score: Mapped[float | None] = mapped_column()
    confidence: Mapped[float | None] = mapped_column()
    risk_flags_json: Mapped[str | None] = mapped_column(Text)
    # 结构化维度分 + 证据（Pydantic 强校验后才落库）
    dimension_json: Mapped[str | None] = mapped_column(Text)
    # L1 轻量特征（章节齐备度/图表数/公式数/页数等）
    features_json: Mapped[str | None] = mapped_column(Text)
    # 实际评估级别：L1 只粗筛，L2 才有分数与证据
    evaluation_level: Mapped[str] = mapped_column(String(4), default="L1", nullable=False)
    level_reason: Mapped[str | None] = mapped_column(Text)
    # 降级原因：结构化校验失败/超时/无 provider 时记录，人工流程照常
    error_message: Mapped[str | None] = mapped_column(Text)
    rule_version: Mapped[str | None] = mapped_column(String(40))
    authority: Mapped[str] = mapped_column(
        String(20), default=ScoreAuthority.ADVISORY.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default=AIReviewStatus.PENDING.value, nullable=False, index=True
    )
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "version_id", "model_id", "prompt_version", "input_hash",
            name="uq_ai_review_idempotency",
        ),
    )


# ─────────────── ReviewEscalation（确定性复审触发）───────────────
class ReviewEscalation(Base, TimestampMixin):
    """复审触发留档：由确定性规则产生，不用模型判断。

    阈值快照写进 thresholds_json、观测值写进 observed_json，
    规则版本写进 rule_version —— 赛事中途改阈值也能追溯当时为何触发。
    同一作品同一规则只触发一次（幂等），处理状态单独流转。
    """

    __tablename__ = "review_escalations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    competition_id: Mapped[str] = mapped_column(
        ForeignKey("competitions.id"), nullable=False, index=True
    )
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id"), nullable=False, index=True
    )
    rule_code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(40), nullable=False)
    thresholds_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    observed_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    action: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=EscalationStatus.OPEN.value, nullable=False, index=True
    )
    ai_review_id: Mapped[str | None] = mapped_column(ForeignKey("ai_review_records.id"))
    triggered_by_score_id: Mapped[str | None] = mapped_column(ForeignKey("score_records.id"))
    note: Mapped[str | None] = mapped_column(Text)
    handled_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "competition_id", "submission_id", "rule_code",
            name="uq_escalation_once_per_rule",
        ),
    )


# ═══════════════ P1/P2 新增模型 ═══════════════

# ─────────────── 18. Notification（FR-005 站内通知）───────────────
class Notification(Base, TimestampMixin):
    """站内通知：一对一或一对多（按角色广播），记录已读状态。"""

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    competition_id: Mapped[str | None] = mapped_column(
        ForeignKey("competitions.id"), index=True
    )
    # 收件人：指定用户 或 按角色广播（二者其一）
    recipient_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    target_role: Mapped[str | None] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(20), default=NotificationStatus.SENT.value, nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), default="IN_APP", nullable=False)
    read_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ─────────────── 19. ReviewException（FR-017 评审异常）───────────────
class ReviewException(Base, TimestampMixin):
    """评审异常：逾期/拒评/回避冲突，保留原因与操作者，任务可被替换。"""

    __tablename__ = "review_exceptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    competition_id: Mapped[str] = mapped_column(
        ForeignKey("competitions.id"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("review_tasks.id"), nullable=False, index=True
    )
    exception_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # 处理方式：REPLACE（替换专家）/ EXTEND（延长时限）/ MANUAL（标记人工处理）
    action: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(
        String(20), default=ReviewExceptionStatus.OPEN.value, nullable=False, index=True
    )
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    handled_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handling_note: Mapped[str | None] = mapped_column(Text)


# ─────────────── 20. Recheck（FR-018 评审复核）───────────────
class Recheck(Base, TimestampMixin):
    """评审复核：锁定原始评分，另存复核结果， authority=REVIEW。"""

    __tablename__ = "rechecks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    competition_id: Mapped[str] = mapped_column(
        ForeignKey("competitions.id"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("review_tasks.id"), nullable=False, index=True
    )
    original_score_id: Mapped[str] = mapped_column(
        ForeignKey("score_records.id"), nullable=False, index=True
    )
    # 原始评分快照（JSON），锁定不可变
    frozen_original_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=RecheckStatus.PENDING.value, nullable=False, index=True
    )
    revised_dimension_json: Mapped[str | None] = mapped_column(Text)
    revised_total: Mapped[float | None] = mapped_column()
    comment: Mapped[str | None] = mapped_column(Text)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("original_score_id", name="uq_recheck_original_score"),)


# ─────────────── 21. ExportJob（FR-025 数据导出）───────────────
class ExportJob(Base, TimestampMixin):
    """导出任务：记录导出范围、格式、状态与产物存储位置。"""

    __tablename__ = "export_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    competition_id: Mapped[str] = mapped_column(
        ForeignKey("competitions.id"), nullable=False, index=True
    )
    data_kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    export_format: Mapped[str] = mapped_column(String(10), default="CSV", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=ExportStatus.COMPLETED.value, nullable=False, index=True
    )
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


# ─────────────── 22. RevisionReview（FR-028 版本复审）───────────────
class RevisionReview(Base, TimestampMixin):
    """版本复审：追踪初稿到修改稿的问题解决状态与再次评审意见。"""

    __tablename__ = "revision_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    competition_id: Mapped[str] = mapped_column(
        ForeignKey("competitions.id"), nullable=False, index=True
    )
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id"), nullable=False, index=True
    )
    version_id: Mapped[str] = mapped_column(
        ForeignKey("submission_versions.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=RevisionStatus.OPEN.value, nullable=False, index=True
    )
    summary: Mapped[str | None] = mapped_column(Text)
    raised_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


# ─────────────── 23. RevisionIssue（FR-028 复审问题项）───────────────
class RevisionIssue(Base, TimestampMixin):
    """复审问题项：关联到版本，带处理状态。"""

    __tablename__ = "revision_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("revision_reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # 关联到某个版本（可空：初始问题尚未绑定修改稿）
    version_id: Mapped[str | None] = mapped_column(ForeignKey("submission_versions.id"))
    status: Mapped[str] = mapped_column(
        String(20), default=IssueStatus.OPEN.value, nullable=False, index=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text)
    handled_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    review: Mapped["RevisionReview"] = relationship()
