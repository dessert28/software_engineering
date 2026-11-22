"""业务规则：生命周期状态机、成绩汇总、匿名材料。

把这些从路由里抽出来，目的是让规则可单测、可被 HTTP 之外（CLI、定时任务）复用。
"""

from __future__ import annotations

import json
import statistics
from datetime import UTC, datetime

from fastapi import HTTPException, status

from app.core.constants import (
    FORCE_ARCHIVE_SOURCES,
    STATE_TRANSITIONS,
    CompetitionState,
    ReviewTaskStatus,
    ScoreAuthority,
    SubmissionStatus,
)
from app.models import Competition, ReviewTask, ScoreRecord, Submission

# 名次并列判定容差：总分保留两位小数，容差取半个最小单位
TIE_TOLERANCE = 0.005


# ─────────────────── 生命周期 ───────────────────
def allowed_next_states(current: CompetitionState) -> list[CompetitionState]:
    return sorted(STATE_TRANSITIONS.get(current, set()), key=lambda s: s.value)


def validate_transition(current: CompetitionState, target: CompetitionState, reason: str | None) -> None:
    if current == target:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"赛事已处于 {target.value} 状态")

    legal = STATE_TRANSITIONS.get(current, set())
    if target in legal:
        return

    # 特例：从早期状态强制归档，必须给原因
    if target is CompetitionState.ARCHIVED and current in FORCE_ARCHIVE_SOURCES:
        if not reason or not reason.strip():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"从 {current.value} 直接归档属于强制操作，必须在 reason 中说明原因",
            )
        return

    raise HTTPException(
        status.HTTP_409_CONFLICT,
        f"非法状态迁移：{current.value} → {target.value}；允许的下一状态："
        + (", ".join(s.value for s in allowed_next_states(current)) or "无"),
    )


# ─────────────────── 时间窗判断 ───────────────────
def is_submission_open(competition: Competition, now: datetime | None = None) -> bool:
    """提交窗口是否开放：既看状态，也看时间节点，两者都要满足。"""
    now = now or datetime.now(UTC)
    if competition.state != CompetitionState.SUBMISSION_OPEN.value:
        return False
    if competition.submission_opens_at and now < _aware(competition.submission_opens_at):
        return False
    if competition.submission_closes_at and now > _aware(competition.submission_closes_at):
        return False
    return True


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def ensure_submittable(competition: Competition, submission: Submission) -> None:
    if submission.status in (SubmissionStatus.SUBMITTED.value, SubmissionStatus.LOCKED.value):
        raise HTTPException(status.HTTP_409_CONFLICT, "作品已提交，如需修改请先撤回")
    if not is_submission_open(competition):
        raise HTTPException(status.HTTP_409_CONFLICT, "当前不在提交时间窗内")


def ensure_version_before_deadline(competition: Competition, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    if competition.state != CompetitionState.SUBMISSION_OPEN.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "赛事未处于提交开放状态")
    if competition.submission_closes_at and now > _aware(competition.submission_closes_at):
        raise HTTPException(status.HTTP_409_CONFLICT, "已过提交截止时间")


# ─────────────────── 评分汇总 ───────────────────
def compute_total(dimension: dict[str, float], rubric: list[dict[str, object]]) -> float:
    """按权重把维度分折算成百分制总分；缺失维度按 0 计并保持权重归一。"""
    if not dimension:
        return 0.0
    weight_sum = 0.0
    acc = 0.0
    for item in rubric:
        key = str(item["key"])
        weight = float(item["weight"])
        if key in dimension:
            acc += float(dimension[key]) * weight
            weight_sum += weight
    if weight_sum <= 0:
        return 0.0
    # 归一化到 100 分制
    return round(acc / weight_sum, 2)


def aggregate_scores(scores: list[ScoreRecord], strategy: str = "MEAN") -> float:
    """把多位专家的总分汇总成一个最终分。

    strategy:
      MEAN          算术平均
      TRIMMED_MEAN  去掉最高最低后平均（至少 3 位专家才生效）
      MEDIAN        中位数
    """
    values = [s.total_score for s in scores if s.authority != ScoreAuthority.ADVISORY.value]
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 2)

    if strategy == "MEDIAN":
        return round(statistics.median(values), 2)

    if strategy == "TRIMMED_MEAN" and len(values) >= 3:
        ordered = sorted(values)
        trimmed = ordered[1:-1]
        return round(sum(trimmed) / len(trimmed), 2)

    return round(sum(values) / len(values), 2)


def assign_ranks(rows: list[tuple[str, float]]) -> dict[str, int]:
    """并列名次：分数相同共享同一名次，后续名次按位次跳号（1,1,3）。

    并列判定用 0.01 容差，而不是精确相等 —— 浮点累加误差会让本该并列的
    成绩错位（例如 89.99999999 与 90.0）。这也和总分保留两位小数的口径一致。
    """
    ordered = sorted(rows, key=lambda r: (-r[1], r[0]))
    ranks: dict[str, int] = {}
    last_score: float | None = None
    last_rank = 0
    for idx, (key, score) in enumerate(ordered, start=1):
        if last_score is not None and abs(score - last_score) < TIE_TOLERANCE:
            ranks[key] = last_rank
        else:
            ranks[key] = idx
            last_rank = idx
            last_score = score
    return ranks


# ─────────────────── 评审任务 ───────────────────
def mark_overdue(tasks: list[ReviewTask], now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    changed = 0
    for t in tasks:
        if t.status in (ReviewTaskStatus.SUBMITTED.value, ReviewTaskStatus.REPLACED.value):
            continue
        if t.due_at and now > _aware(t.due_at):
            t.status = ReviewTaskStatus.OVERDUE.value
            changed += 1
    return changed


def parse_rubric(rule_profile, fallback: list[dict[str, object]]) -> list[dict[str, object]]:
    if rule_profile is None:
        return fallback
    try:
        data = json.loads(rule_profile.rubric_json or "{}")
    except json.JSONDecodeError:
        return fallback
    items = data.get("items")
    return items if isinstance(items, list) and items else fallback
