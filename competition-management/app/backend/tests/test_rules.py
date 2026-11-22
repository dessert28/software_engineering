"""纯业务规则单测：不碰 HTTP、不碰数据库。"""

from __future__ import annotations

import pytest

from app.core.constants import (
    RUBRIC_ITEMS,
    STATE_TRANSITIONS,
    CompetitionState,
)
from app.models import ReviewTask, ScoreRecord
from app.services.rules import (
    aggregate_scores,
    allowed_next_states,
    assign_ranks,
    compute_total,
    validate_transition,
)


class TestLifecycle:
    def test_draft_only_goes_to_registration(self):
        assert allowed_next_states(CompetitionState.DRAFT) == [
            CompetitionState.REGISTRATION_OPEN
        ]

    def test_archived_is_terminal(self):
        assert allowed_next_states(CompetitionState.ARCHIVED) == []

    def test_every_state_reachable_from_draft(self):
        """从草稿出发能走到每一个状态 —— 防止状态机断链。"""
        seen: set[CompetitionState] = set()
        stack = [CompetitionState.DRAFT]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(STATE_TRANSITIONS.get(cur, set()))
        assert seen == set(CompetitionState)

    def test_legal_transition_passes(self):
        validate_transition(
            CompetitionState.REVIEWING, CompetitionState.RESULT_PENDING, None
        )

    def test_illegal_transition_rejected(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            validate_transition(CompetitionState.DRAFT, CompetitionState.REVIEWING, None)
        assert exc.value.status_code == 409
        assert "非法状态迁移" in exc.value.detail

    def test_same_state_rejected(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            validate_transition(CompetitionState.DRAFT, CompetitionState.DRAFT, None)
        assert exc.value.status_code == 400

    def test_force_archive_requires_reason(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            validate_transition(CompetitionState.DRAFT, CompetitionState.ARCHIVED, None)
        assert exc.value.status_code == 400
        assert "reason" in exc.value.detail

    def test_force_archive_with_reason_passes(self):
        validate_transition(
            CompetitionState.DRAFT, CompetitionState.ARCHIVED, "队伍不足，赛事取消"
        )


class TestScoring:
    def test_weighted_total_full_marks(self):
        assert compute_total({"modeling": 100, "solving": 100, "writing": 100}, RUBRIC_ITEMS) == 100.0

    def test_weighted_total_partial(self):
        # (40*40 + 40*40 + 20*20) / 100 = 36
        assert compute_total({"modeling": 40, "solving": 40, "writing": 20}, RUBRIC_ITEMS) == 36.0

    def test_missing_dimension_renormalises(self):
        # 只有建模一项 90 分，权重归一后仍是 90
        assert compute_total({"modeling": 90}, RUBRIC_ITEMS) == 90.0

    def test_empty_dimension_is_zero(self):
        assert compute_total({}, RUBRIC_ITEMS) == 0.0


def _score(value: float, authority: str = "HUMAN") -> ScoreRecord:
    s = ScoreRecord()
    s.total_score = value
    s.authority = authority
    return s


class TestAggregation:
    def test_mean_of_three(self):
        assert aggregate_scores([_score(80), _score(90), _score(70)], "MEAN") == 80.0

    def test_median(self):
        assert aggregate_scores([_score(80), _score(90), _score(70)], "MEDIAN") == 80.0

    def test_trimmed_mean_drops_extremes(self):
        # [60, 80, 90, 100] 去掉 60 和 100 后为 [80,90] = 85
        scores = [_score(v) for v in (60, 80, 90, 100)]
        assert aggregate_scores(scores, "TRIMMED_MEAN") == 85.0

    def test_trimmed_mean_needs_three(self):
        # 只有 2 位专家时退化为算术平均
        assert aggregate_scores([_score(70), _score(90)], "TRIMMED_MEAN") == 80.0

    def test_advisory_scores_never_counted(self):
        """AI 建议分不能影响最终成绩 —— 这是硬约束。"""
        scores = [_score(80), _score(100, authority="ADVISORY")]
        assert aggregate_scores(scores, "MEAN") == 80.0

    def test_all_advisory_yields_zero(self):
        assert aggregate_scores([_score(99, authority="ADVISORY")], "MEAN") == 0.0

    def test_no_scores_yields_zero(self):
        assert aggregate_scores([], "MEAN") == 0.0


class TestRanking:
    def test_simple_order(self):
        ranks = assign_ranks([("a", 90.0), ("b", 80.0), ("c", 70.0)])
        assert ranks == {"a": 1, "b": 2, "c": 3}

    def test_ties_share_rank_and_skip(self):
        ranks = assign_ranks([("a", 90.0), ("b", 90.0), ("c", 80.0)])
        assert ranks["a"] == 1
        assert ranks["b"] == 1
        assert ranks["c"] == 3

    def test_three_way_tie(self):
        ranks = assign_ranks([("a", 90.0), ("b", 90.0), ("c", 90.0), ("d", 80.0)])
        assert ranks["a"] == ranks["b"] == ranks["c"] == 1
        assert ranks["d"] == 4

    def test_tie_detection_uses_cent_tolerance(self):
        # 逐位比较是坑：浮点误差会让本该并列的成绩错位。
        # 统一按 0.01 容差判定，与总分保留两位小数的口径一致。
        ranks = assign_ranks([("a", 90.0), ("b", 90.004)])
        assert ranks["a"] == ranks["b"] == 1

    def test_scores_differing_by_cent_are_not_tied(self):
        # b 分数更高，所以 b 才是第 1 名
        ranks = assign_ranks([("a", 90.0), ("b", 90.02)])
        assert ranks["b"] == 1 and ranks["a"] == 2


class TestRubricContract:
    def test_weights_sum_to_hundred(self):
        assert sum(int(i["weight"]) for i in RUBRIC_ITEMS) == 100
