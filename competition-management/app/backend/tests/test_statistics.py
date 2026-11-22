"""FR-026 赛事统计 / 平台概览测试。

教师账号不在 conftest 基础账号中，本文件用 SessionLocal + hash_password
自建一个 TEACHER 用户，并用 SessionLocal 直接构造统计所需数据。
"""

from __future__ import annotations

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.core.constants import (
    EnrollmentStatus,
    ResultStatus,
    ReviewTaskStatus,
    Role,
    SubmissionStatus,
    TeamMemberRole,
)
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import (
    Competition,
    CompetitionResult,
    Enrollment,
    ReviewTask,
    Submission,
    Team,
    TeamMember,
    User,
)
from tests.conftest import PASSWORD, login


@pytest_asyncio.fixture
async def teacher_user(client: AsyncClient) -> User:
    """在测试库内创建一个 TEACHER 账号（conftest 只建 5 个基础账号）。"""
    async with SessionLocal() as session:
        user = User(
            email="teacher@test.edu",
            name="指导教师",
            role=Role.TEACHER.value,
            school="浙江树人学院",
            password_hash=hash_password(PASSWORD),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def teacher_headers(client: AsyncClient, teacher_user: User) -> dict[str, str]:
    return await login(client, "teacher@test.edu")


@pytest_asyncio.fixture
async def stats_data(client: AsyncClient, teacher_user: User) -> dict[str, str]:
    """构造 1 个赛事 / 3 支队伍 / 报名 / 提交 / 评审任务 / 成绩。

    教师以 ADVISOR 身份指导 T1、T2；以 MEMBER 身份加入 T3（不应计入范围）。
    返回关键 id 供断言使用。
    """
    async with SessionLocal() as session:
        comp = Competition(title="统计测试赛事", state="DRAFT")
        session.add(comp)
        await session.flush()

        t1 = Team(name="统计一队", competition_id=comp.id)
        t2 = Team(name="统计二队", competition_id=comp.id)
        t3 = Team(name="统计三队", competition_id=comp.id)
        session.add_all([t1, t2, t3])
        await session.flush()

        session.add_all(
            [
                TeamMember(
                    team_id=t1.id,
                    user_id=teacher_user.id,
                    role_in_team=TeamMemberRole.ADVISOR.value,
                ),
                TeamMember(
                    team_id=t2.id,
                    user_id=teacher_user.id,
                    role_in_team=TeamMemberRole.ADVISOR.value,
                ),
                TeamMember(
                    team_id=t3.id,
                    user_id=teacher_user.id,
                    role_in_team=TeamMemberRole.MEMBER.value,
                ),
            ]
        )

        e1 = Enrollment(
            competition_id=comp.id, team_id=t1.id, status=EnrollmentStatus.APPROVED.value
        )
        e2 = Enrollment(
            competition_id=comp.id, team_id=t2.id, status=EnrollmentStatus.APPROVED.value
        )
        e3 = Enrollment(
            competition_id=comp.id, team_id=t3.id, status=EnrollmentStatus.PENDING.value
        )
        session.add_all([e1, e2, e3])
        await session.flush()

        s1 = Submission(enrollment_id=e1.id, status=SubmissionStatus.SUBMITTED.value)
        s2 = Submission(enrollment_id=e2.id, status=SubmissionStatus.DRAFT.value)
        session.add_all([s1, s2])
        await session.flush()

        # 评审任务唯一约束 (submission_id, reviewer_id)：S1、S2 各用两名不同评审
        judge = (await session.execute(select(User).where(User.email == "judge@test.edu"))).scalar_one()
        judge2 = (await session.execute(select(User).where(User.email == "judge2@test.edu"))).scalar_one()
        session.add_all(
            [
                ReviewTask(
                    competition_id=comp.id,
                    submission_id=s1.id,
                    reviewer_id=judge.id,
                    material_ref="stat-m1",
                    status=ReviewTaskStatus.ASSIGNED.value,
                ),
                ReviewTask(
                    competition_id=comp.id,
                    submission_id=s1.id,
                    reviewer_id=judge2.id,
                    material_ref="stat-m2",
                    status=ReviewTaskStatus.SUBMITTED.value,
                ),
                ReviewTask(
                    competition_id=comp.id,
                    submission_id=s2.id,
                    reviewer_id=judge.id,
                    material_ref="stat-m3",
                    status=ReviewTaskStatus.IN_PROGRESS.value,
                ),
                ReviewTask(
                    competition_id=comp.id,
                    submission_id=s2.id,
                    reviewer_id=judge2.id,
                    material_ref="stat-m4",
                    status=ReviewTaskStatus.OVERDUE.value,
                ),
            ]
        )

        session.add_all(
            [
                CompetitionResult(
                    competition_id=comp.id,
                    team_id=t1.id,
                    team_name="统计一队",
                    final_score=90.0,
                    rank=1,
                    award="一等奖",
                    status=ResultStatus.PUBLISHED.value,
                ),
                CompetitionResult(
                    competition_id=comp.id,
                    team_id=t2.id,
                    team_name="统计二队",
                    final_score=80.0,
                    rank=2,
                    award="二等奖",
                    status=ResultStatus.DRAFT.value,
                ),
                CompetitionResult(
                    competition_id=comp.id,
                    team_id=t3.id,
                    team_name="统计三队",
                    final_score=70.0,
                    rank=3,
                    award="三等奖",
                    status=ResultStatus.PUBLISHED.value,
                ),
            ]
        )
        await session.commit()
        return {"competition_id": comp.id, "t1": t1.id, "t2": t2.id, "t3": t3.id}


# ───────────────────── 赛事统计 ─────────────────────
async def test_admin_statistics_exact_counts(
    client: AsyncClient, admin_headers: dict[str, str], stats_data: dict[str, str]
) -> None:
    cid = stats_data["competition_id"]
    resp = await client.get(f"/api/competitions/{cid}/statistics", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    d = resp.json()

    assert d["competition_id"] == cid
    assert d["scope"] == "ALL"
    assert d["computed_at"]

    assert d["enrollment"] == {
        "total": 3,
        "pending": 1,
        "approved": 2,
        "rejected": 0,
        "needs_info": 0,
    }
    assert d["submission"]["total"] == 2
    assert d["submission"]["submitted"] == 1
    assert d["submission"]["draft"] == 1

    assert d["review"]["total_tasks"] == 4
    assert d["review"]["assigned"] == 1
    assert d["review"]["submitted"] == 1
    assert d["review"]["in_progress"] == 1
    assert d["review"]["overdue"] == 1
    assert d["review"]["completion_rate"] == 0.25

    assert d["result"]["total"] == 3
    assert d["result"]["draft"] == 1
    assert d["result"]["published"] == 2
    assert d["result"]["avg_final_score"] == 80.0
    assert d["result"]["max_final_score"] == 90.0
    assert d["result"]["min_final_score"] == 70.0
    assert d["result"]["award_distribution"] == {"一等奖": 1, "二等奖": 1, "三等奖": 1}

    assert d["team"] == {"total": 3, "with_submission": 2}
    assert len(d["notes"]) >= 2


async def test_teacher_scope_excludes_other_teams_and_draft_results(
    client: AsyncClient, teacher_headers: dict[str, str], stats_data: dict[str, str]
) -> None:
    cid = stats_data["competition_id"]
    resp = await client.get(f"/api/competitions/{cid}/statistics", headers=teacher_headers)
    assert resp.status_code == 200, resp.text
    d = resp.json()

    assert d["scope"] == "MY_TEAMS"
    # 教师仅指导 T1、T2；T3 虽以 MEMBER 加入，但非 ADVISOR，不计入范围
    assert d["team"]["total"] == 2
    assert d["enrollment"]["total"] == 2
    assert d["enrollment"]["approved"] == 2

    # result 仅含已发布成绩：T2 的草稿分(80)与 T3 的三等奖均不出现
    assert d["result"]["total"] == 1
    assert d["result"]["draft"] == 0
    assert d["result"]["published"] == 1
    assert d["result"]["avg_final_score"] == 90.0
    assert d["result"]["award_distribution"] == {"一等奖": 1}


async def test_statistics_forbidden_for_captain(
    client: AsyncClient, captain_headers: dict[str, str], stats_data: dict[str, str]
) -> None:
    cid = stats_data["competition_id"]
    resp = await client.get(f"/api/competitions/{cid}/statistics", headers=captain_headers)
    assert resp.status_code == 403


async def test_statistics_competition_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.get("/api/competitions/does-not-exist/statistics", headers=admin_headers)
    assert resp.status_code == 404


# ───────────────────── 平台概览 ─────────────────────
async def test_overview_admin(
    client: AsyncClient, admin_headers: dict[str, str], stats_data: dict[str, str]
) -> None:
    resp = await client.get("/api/statistics/overview", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    d = resp.json()

    assert d["users"]["total"] == 6  # conftest 5 个账号 + 本文件 teacher
    assert d["users"]["by_role"]["ADMIN"] == 1
    assert d["users"]["by_role"]["TEACHER"] == 1
    assert d["competitions"]["by_state"].get("DRAFT", 0) >= 1
    assert d["totals"]["teams"] == 3
    assert d["totals"]["submissions"] == 2
    assert d["totals"]["review_tasks"] == 4
    assert d["totals"]["published_results"] == 2


async def test_overview_forbidden_for_captain(
    client: AsyncClient, captain_headers: dict[str, str]
) -> None:
    resp = await client.get("/api/statistics/overview", headers=captain_headers)
    assert resp.status_code == 403
