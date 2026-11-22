"""领域常量：角色、状态机、评审规则。集中定义，避免字符串散落各处。"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    JUDGE = "JUDGE"
    TEACHER = "TEACHER"
    CAPTAIN = "CAPTAIN"
    MEMBER = "MEMBER"


class CompetitionState(StrEnum):
    DRAFT = "DRAFT"
    REGISTRATION_OPEN = "REGISTRATION_OPEN"
    REGISTRATION_CLOSED = "REGISTRATION_CLOSED"
    QUALIFICATION_REVIEW = "QUALIFICATION_REVIEW"
    RUNNING = "RUNNING"
    SUBMISSION_OPEN = "SUBMISSION_OPEN"
    SUBMISSION_CLOSED = "SUBMISSION_CLOSED"
    REVIEWING = "REVIEWING"
    RESULT_PENDING = "RESULT_PENDING"
    RESULT_PUBLISHED = "RESULT_PUBLISHED"
    APPEAL = "APPEAL"
    ARCHIVED = "ARCHIVED"


# 状态机：当前状态 -> 允许进入的下一状态
# 顺序与 docs/boundary.md 的 12 态生命周期一致
STATE_TRANSITIONS: dict[CompetitionState, set[CompetitionState]] = {
    CompetitionState.DRAFT: {CompetitionState.REGISTRATION_OPEN},
    CompetitionState.REGISTRATION_OPEN: {CompetitionState.REGISTRATION_CLOSED},
    CompetitionState.REGISTRATION_CLOSED: {CompetitionState.QUALIFICATION_REVIEW},
    CompetitionState.QUALIFICATION_REVIEW: {CompetitionState.RUNNING},
    CompetitionState.RUNNING: {CompetitionState.SUBMISSION_OPEN},
    CompetitionState.SUBMISSION_OPEN: {CompetitionState.SUBMISSION_CLOSED},
    CompetitionState.SUBMISSION_CLOSED: {CompetitionState.REVIEWING},
    CompetitionState.REVIEWING: {CompetitionState.RESULT_PENDING},
    CompetitionState.RESULT_PENDING: {CompetitionState.RESULT_PUBLISHED},
    CompetitionState.RESULT_PUBLISHED: {CompetitionState.APPEAL},
    CompetitionState.APPEAL: {CompetitionState.ARCHIVED},
    CompetitionState.ARCHIVED: set(),
}

# 允许直接跳到归档的状态（管理员强制归档，需记录原因）
FORCE_ARCHIVE_SOURCES: set[CompetitionState] = {
    CompetitionState.DRAFT,
    CompetitionState.REGISTRATION_OPEN,
    CompetitionState.REGISTRATION_CLOSED,
}


class EnrollmentStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_INFO = "NEEDS_INFO"


class TeamMemberRole(StrEnum):
    CAPTAIN = "CAPTAIN"
    MEMBER = "MEMBER"
    ADVISOR = "ADVISOR"


class SubmissionStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    WITHDRAWN = "WITHDRAWN"
    LOCKED = "LOCKED"


class ReviewTaskStatus(StrEnum):
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    OVERDUE = "OVERDUE"
    REPLACED = "REPLACED"


class ScoreAuthority(StrEnum):
    """评分权威性。AI 只能写 ADVISORY，永不进入加权。"""

    HUMAN = "HUMAN"
    REVIEW = "REVIEW"
    ADVISORY = "ADVISORY"


class ResultStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"


class AuditAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    TRANSITION = "TRANSITION"
    LOGIN = "LOGIN"
    SUBMIT = "SUBMIT"
    SCORE = "SCORE"
    PUBLISH = "PUBLISH"
    EXPORT = "EXPORT"
    # P1/P2 新增动作
    NOTIFY = "NOTIFY"
    EXCEPTION = "EXCEPTION"
    RECHECK = "RECHECK"
    APPEAL = "APPEAL"
    ARCHIVE = "ARCHIVE"
    # AI 预评级与确定性分流（tech-stack-python §10，功能需求表无独立 FR 编号）
    AI_ASSESS = "AI_ASSESS"
    ESCALATE = "ESCALATE"


# ─────────────── P1/P2 新增状态枚举 ───────────────
class NotificationStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    READ = "READ"
    FAILED = "FAILED"


class AppealStatus(StrEnum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    CLOSED = "CLOSED"


class ReviewExceptionType(StrEnum):
    OVERDUE = "OVERDUE"
    REFUSAL = "REFUSAL"
    CONFLICT = "CONFLICT"
    OTHER = "OTHER"


class ReviewExceptionStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class RecheckStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class ExportStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RevisionStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class IssueStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


# 评分细则维度：初版固定三项，权重合计 100
RUBRIC_ITEMS: list[dict[str, object]] = [
    {"key": "modeling", "label": "模型建立", "weight": 40},
    {"key": "solving", "label": "求解与验证", "weight": 40},
    {"key": "writing", "label": "论文表达", "weight": 20},
]

SCORE_MIN = 0
SCORE_MAX = 100


# ─────────────── AI 预评级 / 分流（tech-stack-python §10）───────────────
class AIReviewStatus(StrEnum):
    """预评级留档状态。FAILED/SKIPPED 都视为「无 AI 参考」，人工流程照常。"""

    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class EvaluationLevel(StrEnum):
    """两级评估：L1 规则粗筛全量，L2 结构化深评只覆盖边界带与候选。"""

    L1 = "L1"
    L2 = "L2"


class RiskFlagCode(StrEnum):
    """L1 可检出的风险信号（只展示给专家标记，不暴露 AI 分数）。"""

    MISSING_SECTION = "MISSING_SECTION"       # 章节齐备度不足
    FEW_FIGURES = "FEW_FIGURES"               # 图表数偏少
    SPARSE_FORMULAS = "SPARSE_FORMULAS"       # 公式数偏少
    PAGE_ANOMALY = "PAGE_ANOMALY"             # 页数异常（过少/过多）
    LOW_EVIDENCE = "LOW_EVIDENCE"             # 证据不足，需人工核实
    OCR_REQUIRED = "OCR_REQUIRED"             # 图片型内容，首版不解析，人工核实
    UNUSUAL_LENGTH = "UNUSUAL_LENGTH"         # 正文长度异常


class EscalationRuleCode(StrEnum):
    """确定性复审触发规则。阈值进 rule_profile，不写死在代码判断里。"""

    SCORE_GAP = "SCORE_GAP"                   # 两位专家总分差超阈值 → 第三位盲评
    AI_HUMAN_GAP = "AI_HUMAN_GAP"             # 专家均分与 AI 参考分差超阈值 → 补充理由
    LOW_CONFIDENCE = "LOW_CONFIDENCE"         # AI 置信度低且处于奖项边界 → 专家组复核
    RISK_CONFIRMED = "RISK_CONFIRMED"         # 专家确认 AI 风险项 → 强制复审
    AWARD_BOUNDARY = "AWARD_BOUNDARY"         # 总分落在奖项分界 ±N 分 → 复审队列


class EscalationStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


# 默认复审阈值：赛事可在 rule_profile.ai_thresholds 里覆盖并留版本记录
DEFAULT_AI_THRESHOLDS: dict[str, float] = {
    "score_gap": 15.0,
    "ai_human_gap": 20.0,
    "low_confidence": 0.6,
    "award_boundary": 3.0,
    "l2_min_page_chars": 200,       # L1 文本量低于此值不进 L2（转 OCR_REQUIRED）
    "l2_risk_candidate": 1,         # 命中风险标记数 >= N 进入 L2
}

# 预评级提示词与规则版本：幂等键的组成部分，改动即视为新一次评估
DEFAULT_AI_MODEL_ID = "heuristic-local-v1"
DEFAULT_AI_PROMPT_VERSION = "v1"
DEFAULT_AI_RULE_VERSION = "rules-v1"
