"""申诉模块测试：提交申诉（FR-022）与处理申诉（FR-023）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.core.constants import CompetitionState, Role, TeamMemberRole
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Competition, TeamMember, User
from tests.conftest import login

REASON = "对最终评分结果有异议，申请对模型建立维度重新复核。"
RESOLUTION = "经复核评分确有误差，予以接受并修正。"


# ───────────────────── 辅助 ─────────────────────
async def _create_competition(client: AsyncClient, headers: dict[str, str], **overrides) -> str:
    now = datetime.now(UTC)
    payload = {
        "title": "申诉测试竞赛",
        "edition": "2026 测试",
        "min_team_size": 1,
        "max_team_size": 3,
        "registration_opens_at": (now - timedelta(days=1)).isoformat(),
        "registration_closes_at": (now + timedelta(days=1)).isoformat(),
        "submission_opens_at": (now + timedelta(days=1)).isoformat(),
        "submission_closes_at": (now + timedelta(days=3)).isoformat(),
    }
    payload.update(overrides)
    resp = await client.post("/api/competitions", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _transition(client: AsyncClient, headers: dict[str, str], comp_id: str, target: str):
    return await client.post(
        f"/api/competitions/{comp_id}/transition",
        json={"target": target},
        headers=headers,
    )


async def _prepare(
    client: AsyncClient,
    admin_headers: dict[str, str],
    captain_headers: dict[str, str],
    state: str = CompetitionState.RESULT_PUBLISHED.value,
):
    """建赛事 → 开放报名 → 建队（创建者自动成为队长）→ 直接设置赛事状态。"""
    comp_id = await _create_competition(client, admin_headers)
    resp = await _transition(client, admin_headers, comp_id, "REGISTRATION_OPEN")
    assert resp.status_code == 200, resp.text
    team = await client.post(
        "/api/teams",
        json={"competition_id": comp_id, "name": "申诉测试队"},
        headers=captain_headers,
    )
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]

    if state != CompetitionState.REGISTRATION_OPEN.value:
        async with SessionLocal() as session:
            comp = await session.get(Competition, comp_id)
            comp.state = state
            await session.commit()
    return comp_id, team_id


def _submit_body(comp_id: str, team_id: str, reason: str = REASON) -> dict[str, str]:
    return {"competition_id": comp_id, "team_id": team_id, "reason": reason}


# ───────────────────── 夹具（不改 conftest）─────────────────────
@pytest_asyncio.fixture
async def teacher_headers(client: AsyncClient) -> dict[str, str]:
    async with SessionLocal() as session:
        session.add(
            User(
                email="teacher@test.edu",
                name="指导教师",
                role=Role.TEACHER.value,
                school="浙江树人学院",
                password_hash=hash_password("Passw0rd!"),
            )
        )
        await session.commit()
    return await login(client, "teacher@test.edu")


@pytest_asyncio.fixture
async def other_captain_headers(client: AsyncClient) -> dict[str, str]:
    async with SessionLocal() as session:
        session.add(
            User(
                email="other-captain@test.edu",
                name="外队队长",
                role=Role.CAPTAIN.value,
                password_hash=hash_password("Passw0rd!"),
            )
        )
        await session.commit()
    return await login(client, "other-captain@test.edu")


# ───────────────────── 提交申诉 ─────────────────────
class TestSubmitAppeal:
    async def test_captain_submit_in_result_published(
        self, client: AsyncClient, admin_headers: dict[str, str], captain_headers: dict[str, str]
    ):
        comp_id, team_id = await _prepare(client, admin_headers, captain_headers)
        resp = await client.post(
            "/api/appeals", json=_submit_body(comp_id, team_id), headers=captain_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "OPEN"
        assert data["appeal_no"].startswith("AP-")
        assert data["competition_id"] == comp_id
        assert data["team_id"] == team_id
        assert data["submitted_by"]

    async def test_draft_state_rejected(
        self, client: AsyncClient, admin_headers: dict[str, str], captain_headers: dict[str, str]
    ):
        comp_id, team_id = await _prepare(
            client, admin_headers, captain_headers, state=CompetitionState.DRAFT.value
        )
        resp = await client.post(
            "/api/appeals", json=_submit_body(comp_id, team_id), headers=captain_headers
        )
        assert resp.status_code == 409
        assert "申诉受理期" in resp.json()["detail"]

    async def test_duplicate_appeal_rejected(
        self, client: AsyncClient, admin_headers: dict[str, str], captain_headers: dict[str, str]
    ):
        comp_id, team_id = await _prepare(client, admin_headers, captain_headers)
        body = _submit_body(comp_id, team_id)
        assert (
            await client.post("/api/appeals", json=body, headers=captain_headers)
        ).status_code == 200
        second = await client.post("/api/appeals", json=body, headers=captain_headers)
        assert second.status_code == 409
        assert "已有处理中的申诉" in second.json()["detail"]

    async def test_short_reason_rejected(
        self, client: AsyncClient, admin_headers: dict[str, str], captain_headers: dict[str, str]
    ):
        comp_id, team_id = await _prepare(client, admin_headers, captain_headers)
        resp = await client.post(
            "/api/appeals",
            json=_submit_body(comp_id, team_id, reason="太短"),
            headers=captain_headers,
        )
        assert resp.status_code == 422

    async def test_teacher_advisor_can_submit(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        captain_headers: dict[str, str],
        teacher_headers: dict[str, str],
    ):
        comp_id, team_id = await _prepare(client, admin_headers, captain_headers)
        async with SessionLocal() as session:
            teacher = (
                await session.execute(select(User).where(User.email == "teacher@test.edu"))
            ).scalar_one()
            session.add(
                TeamMember(
                    team_id=team_id,
                    user_id=teacher.id,
                    role_in_team=TeamMemberRole.ADVISOR.value,
                )
            )
            await session.commit()

        resp = await client.post(
            "/api/appeals", json=_submit_body(comp_id, team_id), headers=teacher_headers
        )
        assert resp.status_code == 200, resp.text


# ───────────────────── 查询 ─────────────────────
class TestQueryAppeal:
    async def test_mine_and_admin_list(
        self, client: AsyncClient, admin_headers: dict[str, str], captain_headers: dict[str, str]
    ):
        comp_id, team_id = await _prepare(client, admin_headers, captain_headers)
        appeal_id = (
            await client.post(
                "/api/appeals", json=_submit_body(comp_id, team_id), headers=captain_headers
            )
        ).json()["id"]

        mine = await client.get("/api/appeals/mine", headers=captain_headers)
        assert mine.status_code == 200
        assert any(a["id"] == appeal_id for a in mine.json())

        admin_list = await client.get(
            f"/api/competitions/{comp_id}/appeals", headers=admin_headers
        )
        assert admin_list.status_code == 200
        assert any(a["id"] == appeal_id for a in admin_list.json())

    async def test_other_captain_cannot_read(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        captain_headers: dict[str, str],
        other_captain_headers: dict[str, str],
    ):
        comp_id, team_id = await _prepare(client, admin_headers, captain_headers)
        appeal_id = (
            await client.post(
                "/api/appeals", json=_submit_body(comp_id, team_id), headers=captain_headers
            )
        ).json()["id"]

        resp = await client.get(f"/api/appeals/{appeal_id}", headers=other_captain_headers)
        assert resp.status_code == 403

    async def test_submitter_can_read_detail(
        self, client: AsyncClient, admin_headers: dict[str, str], captain_headers: dict[str, str]
    ):
        comp_id, team_id = await _prepare(client, admin_headers, captain_headers)
        appeal_id = (
            await client.post(
                "/api/appeals", json=_submit_body(comp_id, team_id), headers=captain_headers
            )
        ).json()["id"]

        resp = await client.get(f"/api/appeals/{appeal_id}", headers=captain_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == appeal_id


# ───────────────────── 处理申诉 ─────────────────────
class TestHandleAppeal:
    async def test_assign_then_decide_with_audit(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        captain_headers: dict[str, str],
        judge_id: str,
    ):
        comp_id, team_id = await _prepare(client, admin_headers, captain_headers)
        appeal_id = (
            await client.post(
                "/api/appeals", json=_submit_body(comp_id, team_id), headers=captain_headers
            )
        ).json()["id"]

        assigned = await client.post(
            f"/api/appeals/{appeal_id}/assign",
            json={"handler_id": judge_id},
            headers=admin_headers,
        )
        assert assigned.status_code == 200, assigned.text
        assert assigned.json()["status"] == "ASSIGNED"
        assert assigned.json()["handled_by"] == judge_id

        # 非 OPEN 状态不能再次指派
        dup = await client.post(
            f"/api/appeals/{appeal_id}/assign",
            json={"handler_id": judge_id},
            headers=admin_headers,
        )
        assert dup.status_code == 409

        decided = await client.post(
            f"/api/appeals/{appeal_id}/decide",
            json={"decision": "ACCEPTED", "resolution": RESOLUTION},
            headers=admin_headers,
        )
        assert decided.status_code == 200, decided.text
        data = decided.json()
        assert data["status"] == "ACCEPTED"
        assert data["decision"] == "ACCEPTED"
        assert data["resolution"] == RESOLUTION
        assert data["handled_at"] is not None

        logs = await client.get(
            "/api/audit",
            params={"object_id": appeal_id, "action": "APPEAL"},
            headers=admin_headers,
        )
        assert logs.status_code == 200
        assert len(logs.json()) >= 3  # 提交 + 指派 + 裁决

    async def test_assigned_handler_can_decide(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        captain_headers: dict[str, str],
        judge_headers: dict[str, str],
        judge_id: str,
    ):
        comp_id, team_id = await _prepare(client, admin_headers, captain_headers)
        appeal_id = (
            await client.post(
                "/api/appeals", json=_submit_body(comp_id, team_id), headers=captain_headers
            )
        ).json()["id"]
        await client.post(
            f"/api/appeals/{appeal_id}/assign",
            json={"handler_id": judge_id},
            headers=admin_headers,
        )

        decided = await client.post(
            f"/api/appeals/{appeal_id}/decide",
            json={"decision": "REJECTED", "resolution": "复核后维持原评分结果。"},
            headers=judge_headers,
        )
        assert decided.status_code == 200, decided.text
        assert decided.json()["status"] == "REJECTED"
        assert decided.json()["decision"] == "REJECTED"

    async def test_non_handler_cannot_decide(
        self, client: AsyncClient, admin_headers: dict[str, str], captain_headers: dict[str, str], judge_id: str
    ):
        comp_id, team_id = await _prepare(client, admin_headers, captain_headers)
        appeal_id = (
            await client.post(
                "/api/appeals", json=_submit_body(comp_id, team_id), headers=captain_headers
            )
        ).json()["id"]
        await client.post(
            f"/api/appeals/{appeal_id}/assign",
            json={"handler_id": judge_id},
            headers=admin_headers,
        )

        denied = await client.post(
            f"/api/appeals/{appeal_id}/decide",
            json={"decision": "ACCEPTED", "resolution": "越权裁决尝试。"},
            headers=captain_headers,
        )
        assert denied.status_code == 403
