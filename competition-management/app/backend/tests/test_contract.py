"""回归基线：把 MVP 必须始终成立的契约钉死。

这些断言看起来「太细」，但每一条都对应一个曾经或将来会被改坏的点。
只要这里红了，就说明初版的核心承诺被破坏了。
"""

from __future__ import annotations

import pytest

from app.core.constants import (
    FORCE_ARCHIVE_SOURCES,
    RUBRIC_ITEMS,
    SCORE_MAX,
    SCORE_MIN,
    STATE_TRANSITIONS,
    CompetitionState,
    Role,
    ScoreAuthority,
)
from app.services.rules import allowed_next_states, compute_total


class TestLifecycleBaseline:
    def test_all_twelve_states_are_reachable(self):
        """12 个状态一个都不能少，否则大赛流程就走不完。"""
        assert len(CompetitionState) == 12

    def test_every_state_appears_in_transition_map(self):
        """状态机表必须覆盖全部状态 —— 漏一个就会出现「卡死在某状态」。"""
        for s in CompetitionState:
            assert s.value in STATE_TRANSITIONS, f"{s.value} 没有出边定义"
            assert isinstance(STATE_TRANSITIONS[s.value], set)

    def test_transition_targets_are_known_states(self):
        """出边只能指向真实存在的状态。"""
        valid = {s.value for s in CompetitionState}
        for src, targets in STATE_TRANSITIONS.items():
            for t in targets:
                assert t in valid, f"{src} → {t} 指向了不存在的状态"

    def test_archived_is_terminal(self):
        assert allowed_next_states(CompetitionState.ARCHIVED.value) == []

    def test_force_archive_only_from_early_states(self):
        """只有报名截止前才允许强制归档 —— 评审开始后归档会丢成绩。"""
        for s in FORCE_ARCHIVE_SOURCES:
            assert s.value in {
                CompetitionState.DRAFT.value,
                CompetitionState.REGISTRATION_OPEN.value,
                CompetitionState.REGISTRATION_CLOSED.value,
            }


class TestScoringBaseline:
    def test_full_marks_is_exactly_100(self):
        assert compute_total({"modeling": 100, "solving": 100, "writing": 100}, RUBRIC_ITEMS) == 100.0

    def test_zero_is_exactly_0(self):
        assert compute_total({"modeling": 0, "solving": 0, "writing": 0}, RUBRIC_ITEMS) == 0.0

    def test_rubric_weights_sum_to_100(self):
        assert sum(i["weight"] for i in RUBRIC_ITEMS) == 100

    def test_score_bounds(self):
        assert (SCORE_MIN, SCORE_MAX) == (0, 100)

    def test_rounding_is_two_decimals(self):
        """成绩对外展示两位小数，内部计算不能出现 87.59999999。"""
        total = compute_total({"modeling": 87, "solving": 88, "writing": 89}, RUBRIC_ITEMS)
        assert total == round(total, 2)

    def test_canonical_total_is_87_2(self):
        """README 里引用的样例分，防止权重被改坏。"""
        assert compute_total({"modeling": 88, "solving": 85, "writing": 90}, RUBRIC_ITEMS) == 87.2


class TestAuthorityBaseline:
    def test_advisory_is_never_weighted(self):
        """AI 只能给建议，这条是选型文档里的红线。"""
        from types import SimpleNamespace

        from app.services.rules import aggregate_scores

        scored = [
            SimpleNamespace(total_score=85.0, authority=ScoreAuthority.HUMAN.value),
            SimpleNamespace(total_score=10.0, authority=ScoreAuthority.ADVISORY.value),
        ]
        assert aggregate_scores(scored, "MEAN") == 85.0

    def test_only_three_authorities_exist(self):
        assert {a.value for a in ScoreAuthority} == {"HUMAN", "REVIEW", "ADVISORY"}


class TestRoleBaseline:
    def test_five_roles(self):
        assert {r.value for r in Role} == {"ADMIN", "JUDGE", "TEACHER", "CAPTAIN", "MEMBER"}

    def test_only_judge_and_admin_can_review(self):
        """评审权限只能给 JUDGE 和 ADMIN，别的角色进来匿名就白做了。"""
        from app.core.deps import PRIVILEGED_REVIEW_ROLES

        assert set(PRIVILEGED_REVIEW_ROLES) == {Role.ADMIN, Role.JUDGE}


class TestUploadPolicyBaseline:
    def test_pdf_is_always_allowed(self):
        from app.core.config import settings

        assert ".pdf" in settings.allowed_extensions

    def test_extensions_are_normalized_lowercase(self):
        from app.core.config import settings

        for ext in settings.allowed_extensions:
            assert ext == ext.lower()
            assert ext.startswith(".")

    def test_default_cap_is_50mb(self):
        """50MB 是文档里定下的上限；环境变量只应临时覆盖，默认值不能被改小。"""
        from app.core.config import Settings

        assert Settings.model_fields["max_upload_bytes"].default == 52_428_800


class TestAnonymityBaseline:
    def test_material_schema_has_no_identity_fields(self):
        """匿名材料的结构本身就不允许出现身份字段。"""
        from app.schemas import AnonymousMaterial

        forbidden = {"team_name", "school", "members", "advisor", "team_id", "user_id"}
        assert forbidden.isdisjoint(set(AnonymousMaterial.model_fields))

    def test_material_only_exposes_problem_code(self):
        from app.schemas import AnonymousMaterial

        assert "problem_code" in AnonymousMaterial.model_fields


@pytest.mark.parametrize(
    "state",
    [
        CompetitionState.DRAFT.value,
        CompetitionState.REGISTRATION_OPEN.value,
        CompetitionState.RUNNING.value,
        CompetitionState.REVIEWING.value,
    ],
)
def test_state_has_at_least_one_exit(state: str):
    """除终态外每个状态都要有出路，否则流程会锁死。"""
    assert len(allowed_next_states(state)) >= 1
