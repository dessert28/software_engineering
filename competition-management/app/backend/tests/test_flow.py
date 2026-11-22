"""端到端测试：把 FR 主链路完整走一遍。

这不是「每个接口各测一次」，而是按真实业务流程串联：
建赛事 → 开放报名 → 建队 → 报名 → 审核 → 提交 → 锁窗 → 分配评审
→ 匿名查看 → 打分 → 汇总 → 发布 → 越权检查。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import login


async def _create_competition(client, headers, **overrides) -> str:
    now = datetime.now(UTC)
    payload = {
        "title": "测试用数学建模竞赛",
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


async def _transition(client, headers, comp_id, target, reason=None):
    body = {"target": target}
    if reason:
        body["reason"] = reason
    return await client.post(f"/api/competitions/{comp_id}/transition", json=body, headers=headers)


class TestAuth:
    async def test_login_success(self, client):
        resp = await client.post(
            "/api/auth/login", json={"email": "admin@test.edu", "password": "Passw0rd!"}
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["role"] == "ADMIN"
        assert resp.json()["access_token"]

    async def test_login_wrong_password(self, client):
        resp = await client.post(
            "/api/auth/login", json={"email": "admin@test.edu", "password": "wrong-pass"}
        )
        assert resp.status_code == 401

    async def test_login_unknown_email(self, client):
        resp = await client.post(
            "/api/auth/login", json={"email": "nobody@test.edu", "password": "Passw0rd!"}
        )
        assert resp.status_code == 401

    async def test_me_requires_token(self, client):
        assert (await client.get("/api/auth/me")).status_code == 401

    async def test_me_with_token(self, client, admin_headers):
        resp = await client.get("/api/auth/me", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == "admin@test.edu"


class TestCompetitionLifecycle:
    async def test_create_returns_draft(self, client, admin_headers):
        comp_id = await _create_competition(client, admin_headers)
        resp = await client.get(f"/api/competitions/{comp_id}", headers=admin_headers)
        assert resp.json()["state"] == "DRAFT"

    async def test_time_order_validated(self, client, admin_headers):
        now = datetime.now(UTC)
        resp = await client.post(
            "/api/competitions",
            json={
                "title": "时间倒挂赛事",
                "registration_opens_at": (now + timedelta(days=2)).isoformat(),
                "registration_closes_at": (now + timedelta(days=1)).isoformat(),
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422

    async def test_non_admin_cannot_create(self, client, captain_headers):
        now = datetime.now(UTC)
        resp = await client.post(
            "/api/competitions",
            json={"title": "越权赛事", "registration_opens_at": now.isoformat()},
            headers=captain_headers,
        )
        assert resp.status_code == 403

    async def test_full_state_walk(self, client, admin_headers):
        """按 12 态顺序一路推到归档。"""
        comp_id = await _create_competition(client, admin_headers)
        walk = [
            "REGISTRATION_OPEN",
            "REGISTRATION_CLOSED",
            "QUALIFICATION_REVIEW",
            "RUNNING",
            "SUBMISSION_OPEN",
            "SUBMISSION_CLOSED",
            "REVIEWING",
            "RESULT_PENDING",
            "RESULT_PUBLISHED",
            "APPEAL",
            "ARCHIVED",
        ]
        for target in walk:
            resp = await _transition(client, admin_headers, comp_id, target)
            assert resp.status_code == 200, f"{target}: {resp.text}"

    async def test_illegal_jump_rejected(self, client, admin_headers):
        comp_id = await _create_competition(client, admin_headers)
        resp = await _transition(client, admin_headers, comp_id, "REVIEWING")
        assert resp.status_code == 409
        assert "非法状态迁移" in resp.json()["detail"]

    async def test_force_archive_needs_reason(self, client, admin_headers):
        comp_id = await _create_competition(client, admin_headers)
        resp = await _transition(client, admin_headers, comp_id, "ARCHIVED")
        assert resp.status_code == 400

        resp = await _transition(client, admin_headers, comp_id, "ARCHIVED", "赛事取消")
        assert resp.status_code == 200
        assert resp.json()["competition"]["state"] == "ARCHIVED"

    async def test_archived_cannot_be_edited(self, client, admin_headers):
        comp_id = await _create_competition(client, admin_headers)
        await _transition(client, admin_headers, comp_id, "ARCHIVED", "取消")
        resp = await client.patch(
            f"/api/competitions/{comp_id}", json={"title": "改名"}, headers=admin_headers
        )
        assert resp.status_code == 409

    async def test_transition_writes_audit_log(self, client, admin_headers):
        comp_id = await _create_competition(client, admin_headers)
        await _transition(client, admin_headers, comp_id, "REGISTRATION_OPEN")
        resp = await client.get(
            "/api/audit", params={"object_id": comp_id, "action": "TRANSITION"}, headers=admin_headers
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestTeamAndEnrollment:
    async def test_create_team_requires_registration_open(self, client, admin_headers, captain_headers):
        comp_id = await _create_competition(client, admin_headers)
        resp = await client.post(
            "/api/teams",
            json={"competition_id": comp_id, "name": "草稿期队伍"},
            headers=captain_headers,
        )
        assert resp.status_code == 409

    async def test_duplicate_team_name_rejected(self, client, admin_headers, captain_headers):
        comp_id = await _create_competition(client, admin_headers)
        await _transition(client, admin_headers, comp_id, "REGISTRATION_OPEN")

        first = await client.post(
            "/api/teams",
            json={"competition_id": comp_id, "name": "重名队"},
            headers=captain_headers,
        )
        assert first.status_code == 201

        second = await client.post(
            "/api/teams",
            json={"competition_id": comp_id, "name": "重名队"},
            headers=captain_headers,
        )
        assert second.status_code == 409

    async def test_creator_becomes_captain(self, client, admin_headers, captain_headers):
        comp_id = await _create_competition(client, admin_headers)
        await _transition(client, admin_headers, comp_id, "REGISTRATION_OPEN")
        resp = await client.post(
            "/api/teams",
            json={"competition_id": comp_id, "name": "自动队长队"},
            headers=captain_headers,
        )
        members = resp.json()["members"]
        assert len(members) == 1
        assert members[0]["role_in_team"] == "CAPTAIN"

    async def test_member_limit_enforced(self, client, admin_headers, captain_headers):
        comp_id = await _create_competition(client, admin_headers, max_team_size=1)
        await _transition(client, admin_headers, comp_id, "REGISTRATION_OPEN")
        team = await client.post(
            "/api/teams",
            json={"competition_id": comp_id, "name": "单人队"},
            headers=captain_headers,
        )
        team_id = team.json()["id"]

        resp = await client.post(
            f"/api/teams/{team_id}/members",
            json={"email": "member@test.edu", "role_in_team": "MEMBER"},
            headers=captain_headers,
        )
        assert resp.status_code == 409

    async def test_advisor_does_not_count_toward_limit(self, client, admin_headers, captain_headers):
        comp_id = await _create_competition(client, admin_headers, max_team_size=1)
        await _transition(client, admin_headers, comp_id, "REGISTRATION_OPEN")
        team = await client.post(
            "/api/teams",
            json={"competition_id": comp_id, "name": "带指导队"},
            headers=captain_headers,
        )
        team_id = team.json()["id"]

        resp = await client.post(
            f"/api/teams/{team_id}/members",
            json={"email": "teacher@test.edu", "role_in_team": "ADVISOR"},
            headers=captain_headers,
        )
        # teacher@test.edu 在测试库中不存在（夹具只建了 5 个账号），
        # 这里应该因为缺少 name 而报错，而不是因为人数超限
        assert resp.status_code == 400

    async def test_enrollment_review_flow(self, client, admin_headers, captain_headers):
        comp_id = await _create_competition(client, admin_headers)
        await _transition(client, admin_headers, comp_id, "REGISTRATION_OPEN")
        team = await client.post(
            "/api/teams",
            json={"competition_id": comp_id, "name": "审核流程队"},
            headers=captain_headers,
        )
        team_id = team.json()["id"]

        enr = await client.post(
            "/api/enrollments",
            json={"competition_id": comp_id, "team_id": team_id},
            headers=captain_headers,
        )
        assert enr.status_code == 201
        assert enr.json()["status"] == "PENDING"
        enr_id = enr.json()["id"]

        # 非管理员不能审核
        deny = await client.post(
            f"/api/enrollments/{enr_id}/review",
            json={"status": "APPROVED"},
            headers=captain_headers,
        )
        assert deny.status_code == 403

        ok = await client.post(
            f"/api/enrollments/{enr_id}/review",
            json={"status": "APPROVED", "comment": "材料齐全"},
            headers=admin_headers,
        )
        assert ok.status_code == 200
        assert ok.json()["status"] == "APPROVED"

    async def test_duplicate_enrollment_rejected(self, client, admin_headers, captain_headers):
        comp_id = await _create_competition(client, admin_headers)
        await _transition(client, admin_headers, comp_id, "REGISTRATION_OPEN")
        team = await client.post(
            "/api/teams",
            json={"competition_id": comp_id, "name": "重复报名队"},
            headers=captain_headers,
        )
        team_id = team.json()["id"]
        body = {"competition_id": comp_id, "team_id": team_id}

        assert (
            await client.post("/api/enrollments", json=body, headers=captain_headers)
        ).status_code == 201
        second = await client.post("/api/enrollments", json=body, headers=captain_headers)
        assert second.status_code == 409


class TestSubmission:
    async def _prepare(self, client, admin_headers, captain_headers):
        """建赛事 → 开放报名 → 建队 → 报名 → 审核通过 → 推到提交开放。"""
        now = datetime.now(UTC)
        comp_id = await _create_competition(
            client,
            admin_headers,
            submission_opens_at=(now - timedelta(hours=1)).isoformat(),
            submission_closes_at=(now + timedelta(days=2)).isoformat(),
        )
        await _transition(client, admin_headers, comp_id, "REGISTRATION_OPEN")

        team = await client.post(
            "/api/teams",
            json={"competition_id": comp_id, "name": "提交测试队"},
            headers=captain_headers,
        )
        team_id = team.json()["id"]

        enr = await client.post(
            "/api/enrollments",
            json={"competition_id": comp_id, "team_id": team_id},
            headers=captain_headers,
        )
        enr_id = enr.json()["id"]

        await client.post(
            f"/api/enrollments/{enr_id}/review",
            json={"status": "APPROVED"},
            headers=admin_headers,
        )

        for target in ("REGISTRATION_CLOSED", "QUALIFICATION_REVIEW", "RUNNING", "SUBMISSION_OPEN"):
            await _transition(client, admin_headers, comp_id, target)

        return comp_id, team_id, enr_id

    async def test_upload_and_submit(self, client, admin_headers, captain_headers):
        _, _, enr_id = await self._prepare(client, admin_headers, captain_headers)

        sub = await client.post(
            f"/api/submissions/by-enrollment/{enr_id}", headers=captain_headers
        )
        assert sub.status_code == 201
        sub_id = sub.json()["id"]

        up = await client.post(
            f"/api/submissions/{sub_id}/versions",
            files={"file": ("paper.pdf", b"%PDF-1.4 test content", "application/pdf")},
            data={"note": "初稿"},
            headers=captain_headers,
        )
        assert up.status_code == 201, up.text
        assert up.json()["version_no"] == 1

        done = await client.post(f"/api/submissions/{sub_id}/submit", headers=captain_headers)
        assert done.status_code == 200
        assert done.json()["status"] == "SUBMITTED"

    async def test_version_numbers_increment(self, client, admin_headers, captain_headers):
        _, _, enr_id = await self._prepare(client, admin_headers, captain_headers)
        sub_id = (
            await client.post(f"/api/submissions/by-enrollment/{enr_id}", headers=captain_headers)
        ).json()["id"]

        for expected in (1, 2, 3):
            resp = await client.post(
                f"/api/submissions/{sub_id}/versions",
                files={"file": (f"v{expected}.pdf", f"content-{expected}".encode(), "application/pdf")},
                headers=captain_headers,
            )
            assert resp.status_code == 201
            assert resp.json()["version_no"] == expected

    async def test_wrong_extension_rejected(self, client, admin_headers, captain_headers):
        _, _, enr_id = await self._prepare(client, admin_headers, captain_headers)
        sub_id = (
            await client.post(f"/api/submissions/by-enrollment/{enr_id}", headers=captain_headers)
        ).json()["id"]

        resp = await client.post(
            f"/api/submissions/{sub_id}/versions",
            files={"file": ("evil.exe", b"MZ\x90\x00", "application/octet-stream")},
            headers=captain_headers,
        )
        assert resp.status_code == 415

    async def test_empty_file_rejected(self, client, admin_headers, captain_headers):
        _, _, enr_id = await self._prepare(client, admin_headers, captain_headers)
        sub_id = (
            await client.post(f"/api/submissions/by-enrollment/{enr_id}", headers=captain_headers)
        ).json()["id"]

        resp = await client.post(
            f"/api/submissions/{sub_id}/versions",
            files={"file": ("empty.pdf", b"", "application/pdf")},
            headers=captain_headers,
        )
        assert resp.status_code == 400

    async def test_submit_without_version_rejected(self, client, admin_headers, captain_headers):
        _, _, enr_id = await self._prepare(client, admin_headers, captain_headers)
        sub_id = (
            await client.post(f"/api/submissions/by-enrollment/{enr_id}", headers=captain_headers)
        ).json()["id"]

        resp = await client.post(f"/api/submissions/{sub_id}/submit", headers=captain_headers)
        assert resp.status_code == 409
        assert "尚未上传" in resp.json()["detail"]

    async def test_duplicate_submit_rejected(self, client, admin_headers, captain_headers):
        _, _, enr_id = await self._prepare(client, admin_headers, captain_headers)
        sub_id = (
            await client.post(f"/api/submissions/by-enrollment/{enr_id}", headers=captain_headers)
        ).json()["id"]
        await client.post(
            f"/api/submissions/{sub_id}/versions",
            files={"file": ("a.pdf", b"data", "application/pdf")},
            headers=captain_headers,
        )
        await client.post(f"/api/submissions/{sub_id}/submit", headers=captain_headers)

        again = await client.post(f"/api/submissions/{sub_id}/submit", headers=captain_headers)
        assert again.status_code == 409

    async def test_submission_locked_after_deadline(
        self, client, admin_headers, captain_headers
    ):
        """截止时间过了就不能再提交 —— 这条是硬约束。"""
        now = datetime.now(UTC)
        comp_id = await _create_competition(
            client,
            admin_headers,
            submission_opens_at=(now - timedelta(hours=2)).isoformat(),
            submission_closes_at=(now - timedelta(hours=1)).isoformat(),  # 已过期
        )
        await _transition(client, admin_headers, comp_id, "REGISTRATION_OPEN")
        team = await client.post(
            "/api/teams",
            json={"competition_id": comp_id, "name": "过期队"},
            headers=captain_headers,
        )
        enr = await client.post(
            "/api/enrollments",
            json={"competition_id": comp_id, "team_id": team.json()["id"]},
            headers=captain_headers,
        )
        enr_id = enr.json()["id"]
        await client.post(
            f"/api/enrollments/{enr_id}/review",
            json={"status": "APPROVED"},
            headers=admin_headers,
        )
        for target in ("REGISTRATION_CLOSED", "QUALIFICATION_REVIEW", "RUNNING", "SUBMISSION_OPEN"):
            await _transition(client, admin_headers, comp_id, target)

        sub_id = (
            await client.post(f"/api/submissions/by-enrollment/{enr_id}", headers=captain_headers)
        ).json()["id"]
        resp = await client.post(
            f"/api/submissions/{sub_id}/versions",
            files={"file": ("late.pdf", b"data", "application/pdf")},
            headers=captain_headers,
        )
        assert resp.status_code == 409
        assert "截止" in resp.json()["detail"]


async def prepare_reviewable(client, admin_headers, captain_headers):
    """一路推进到 REVIEWING，返回 (comp_id, submission_id, judge_id)。

    放在模块级，方便不同测试类共用 —— 这条链路有 8 步，复制多份迟早会走样。
    """
    now = datetime.now(UTC)
    comp_id = await _create_competition(
        client,
        admin_headers,
        submission_opens_at=(now - timedelta(hours=1)).isoformat(),
        submission_closes_at=(now + timedelta(days=2)).isoformat(),
    )
    await _transition(client, admin_headers, comp_id, "REGISTRATION_OPEN")
    team = await client.post(
        "/api/teams",
        json={"competition_id": comp_id, "name": "评审测试队", "school": "浙江树人学院"},
        headers=captain_headers,
    )
    enr = await client.post(
        "/api/enrollments",
        json={"competition_id": comp_id, "team_id": team.json()["id"]},
        headers=captain_headers,
    )
    enr_id = enr.json()["id"]
    await client.post(
        f"/api/enrollments/{enr_id}/review",
        json={"status": "APPROVED"},
        headers=admin_headers,
    )
    for target in ("REGISTRATION_CLOSED", "QUALIFICATION_REVIEW", "RUNNING", "SUBMISSION_OPEN"):
        await _transition(client, admin_headers, comp_id, target)

    sub_id = (
        await client.post(f"/api/submissions/by-enrollment/{enr_id}", headers=captain_headers)
    ).json()["id"]
    await client.post(
        f"/api/submissions/{sub_id}/versions",
        files={"file": ("paper.pdf", b"%PDF content", "application/pdf")},
        headers=captain_headers,
    )
    await client.post(f"/api/submissions/{sub_id}/submit", headers=captain_headers)

    for target in ("SUBMISSION_CLOSED", "REVIEWING"):
        await _transition(client, admin_headers, comp_id, target)

    judges = (await client.get("/api/judges", headers=admin_headers)).json()
    judge_id = [j for j in judges if j["email"] == "judge@test.edu"][0]["id"]

    return comp_id, sub_id, judge_id


class TestReviewAndResult:
    async def _prepare_reviewable(self, client, admin_headers, captain_headers, judge_headers):
        return await prepare_reviewable(client, admin_headers, captain_headers)

    async def test_assign_task_and_score(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        comp_id, sub_id, judge_id = await self._prepare_reviewable(
            client, admin_headers, captain_headers, judge_headers
        )

        task = await client.post(
            "/api/review-tasks",
            json={
                "competition_id": comp_id,
                "submission_id": sub_id,
                "reviewer_id": judge_id,
            },
            headers=admin_headers,
        )
        assert task.status_code == 201, task.text
        task_id = task.json()["id"]
        assert task.json()["material_ref"]

        material = await client.get(f"/api/review-tasks/{task_id}/material", headers=judge_headers)
        assert material.status_code == 200
        body = material.json()
        # 匿名性：材料里不能出现队伍名
        assert "评审测试队" not in str(body)
        assert material.json()["problem_code"].startswith("作品编号")

        score = await client.post(
            f"/api/review-tasks/{task_id}/score",
            json={
                "dimension": {"modeling": 88, "solving": 85, "writing": 90},
                "comment": "模型假设清晰，求解过程完整，论文表述规范。",
            },
            headers=judge_headers,
        )
        assert score.status_code == 200, score.text
        assert score.json()["authority"] == "HUMAN"
        # (88*40 + 85*40 + 90*20) / 100 = 87.2
        assert score.json()["total_score"] == 87.2

    async def test_self_review_blocked(self, client, admin_headers, captain_headers, judge_headers):
        comp_id, sub_id, judge_id = await self._prepare_reviewable(
            client, admin_headers, captain_headers, judge_headers
        )
        task = await client.post(
            "/api/review-tasks",
            json={"competition_id": comp_id, "submission_id": sub_id, "reviewer_id": judge_id},
            headers=admin_headers,
        )
        task_id = task.json()["id"]

        # 队长不是评审专家，读材料应被拒
        resp = await client.get(f"/api/review-tasks/{task_id}/material", headers=captain_headers)
        assert resp.status_code == 403

    async def test_short_comment_rejected(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        comp_id, sub_id, judge_id = await self._prepare_reviewable(
            client, admin_headers, captain_headers, judge_headers
        )
        task_id = (
            await client.post(
                "/api/review-tasks",
                json={"competition_id": comp_id, "submission_id": sub_id, "reviewer_id": judge_id},
                headers=admin_headers,
            )
        ).json()["id"]

        resp = await client.post(
            f"/api/review-tasks/{task_id}/score",
            json={"dimension": {"modeling": 80}, "comment": "不错"},
            headers=judge_headers,
        )
        assert resp.status_code == 400

    async def test_out_of_range_score_rejected(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        comp_id, sub_id, judge_id = await self._prepare_reviewable(
            client, admin_headers, captain_headers, judge_headers
        )
        task_id = (
            await client.post(
                "/api/review-tasks",
                json={"competition_id": comp_id, "submission_id": sub_id, "reviewer_id": judge_id},
                headers=admin_headers,
            )
        ).json()["id"]

        resp = await client.post(
            f"/api/review-tasks/{task_id}/score",
            json={"dimension": {"modeling": 120}, "comment": "分数越界的评语内容"},
            headers=judge_headers,
        )
        assert resp.status_code == 422

    async def test_duplicate_assignment_rejected(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        comp_id, sub_id, judge_id = await self._prepare_reviewable(
            client, admin_headers, captain_headers, judge_headers
        )
        body = {"competition_id": comp_id, "submission_id": sub_id, "reviewer_id": judge_id}
        assert (await client.post("/api/review-tasks", json=body, headers=admin_headers)).status_code == 201
        assert (await client.post("/api/review-tasks", json=body, headers=admin_headers)).status_code == 409

    async def test_progress_reflects_scoring(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        comp_id, sub_id, judge_id = await self._prepare_reviewable(
            client, admin_headers, captain_headers, judge_headers
        )
        task_id = (
            await client.post(
                "/api/review-tasks",
                json={"competition_id": comp_id, "submission_id": sub_id, "reviewer_id": judge_id},
                headers=admin_headers,
            )
        ).json()["id"]

        before = await client.get(
            f"/api/competitions/{comp_id}/review-progress", headers=admin_headers
        )
        assert before.json()["total_tasks"] == 1
        assert before.json()["submitted"] == 0
        assert before.json()["completion_rate"] == 0.0

        await client.post(
            f"/api/review-tasks/{task_id}/score",
            json={"dimension": {"modeling": 80, "solving": 80, "writing": 80}, "comment": "达到基本要求，模型与求解过程完整。"},
            headers=judge_headers,
        )

        after = await client.get(
            f"/api/competitions/{comp_id}/review-progress", headers=admin_headers
        )
        assert after.json()["submitted"] == 1
        assert after.json()["completion_rate"] == 1.0

    async def test_calculate_and_publish(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        comp_id, sub_id, judge_id = await self._prepare_reviewable(
            client, admin_headers, captain_headers, judge_headers
        )
        task_id = (
            await client.post(
                "/api/review-tasks",
                json={"competition_id": comp_id, "submission_id": sub_id, "reviewer_id": judge_id},
                headers=admin_headers,
            )
        ).json()["id"]
        await client.post(
            f"/api/review-tasks/{task_id}/score",
            json={"dimension": {"modeling": 90, "solving": 90, "writing": 90}, "comment": "模型建立严谨，求解与验证充分。"},
            headers=judge_headers,
        )

        await _transition(client, admin_headers, comp_id, "RESULT_PENDING")

        calc = await client.post(
            f"/api/competitions/{comp_id}/results/calculate", headers=admin_headers
        )
        assert calc.status_code == 200, calc.text
        assert calc.json()["computed"] == 1
        assert calc.json()["results"][0]["final_score"] == 90.0
        assert calc.json()["results"][0]["rank"] == 1

        pub = await client.post(
            f"/api/competitions/{comp_id}/results/publish", headers=admin_headers
        )
        assert pub.status_code == 200
        assert pub.json()[0]["status"] == "PUBLISHED"

    async def test_publish_before_calculate_rejected(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        comp_id, _, _ = await self._prepare_reviewable(
            client, admin_headers, captain_headers, judge_headers
        )
        await _transition(client, admin_headers, comp_id, "RESULT_PENDING")
        resp = await client.post(
            f"/api/competitions/{comp_id}/results/publish", headers=admin_headers
        )
        assert resp.status_code == 409


class TestVisibilityRules:
    async def test_draft_result_hidden_from_captain(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        """未发布的结果对参赛方不可见（FR-020/FR-021）。"""
        comp_id, sub_id, judge_id = await prepare_reviewable(
            client, admin_headers, captain_headers
        )
        task_id = (
            await client.post(
                "/api/review-tasks",
                json={"competition_id": comp_id, "submission_id": sub_id, "reviewer_id": judge_id},
                headers=admin_headers,
            )
        ).json()["id"]
        await client.post(
            f"/api/review-tasks/{task_id}/score",
            json={"dimension": {"modeling": 70, "solving": 70, "writing": 70}, "comment": "基本达标，建议补充灵敏度分析。"},
            headers=judge_headers,
        )
        await _transition(client, admin_headers, comp_id, "RESULT_PENDING")
        await client.post(f"/api/competitions/{comp_id}/results/calculate", headers=admin_headers)

        as_admin = await client.get(f"/api/competitions/{comp_id}/results/all", headers=admin_headers)
        assert len(as_admin.json()) == 1

        as_captain = await client.get(f"/api/competitions/{comp_id}/results", headers=captain_headers)
        assert as_captain.json() == []

    async def test_cannot_read_other_team_submission(
        self, client, admin_headers, captain_headers
    ):
        now = datetime.now(UTC)
        comp_id = await _create_competition(
            client,
            admin_headers,
            submission_opens_at=(now - timedelta(hours=1)).isoformat(),
            submission_closes_at=(now + timedelta(days=2)).isoformat(),
        )
        await _transition(client, admin_headers, comp_id, "REGISTRATION_OPEN")
        team = await client.post(
            "/api/teams",
            json={"competition_id": comp_id, "name": "他人队伍"},
            headers=captain_headers,
        )
        enr = await client.post(
            "/api/enrollments",
            json={"competition_id": comp_id, "team_id": team.json()["id"]},
            headers=captain_headers,
        )
        await client.post(
            f"/api/enrollments/{enr.json()['id']}/review",
            json={"status": "APPROVED"},
            headers=admin_headers,
        )
        for target in ("REGISTRATION_CLOSED", "QUALIFICATION_REVIEW", "RUNNING", "SUBMISSION_OPEN"):
            await _transition(client, admin_headers, comp_id, target)
        sub_id = (
            await client.post(
                f"/api/submissions/by-enrollment/{enr.json()['id']}", headers=captain_headers
            )
        ).json()["id"]

        member_headers = await login(client, "member@test.edu")
        # member 不在队伍里，读提交应被拒
        resp = await client.get(f"/api/submissions/{sub_id}", headers=member_headers)
        assert resp.status_code == 403

    async def test_audit_requires_admin(self, client, captain_headers):
        resp = await client.get("/api/audit", headers=captain_headers)
        assert resp.status_code == 403


class TestMeta:
    async def test_health(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_lifecycle_metadata(self, client):
        resp = await client.get("/api/meta/lifecycle")
        assert resp.status_code == 200
        assert len(resp.json()["states"]) == 12

    async def test_rubric_weights(self, client):
        resp = await client.get("/api/meta/rubric")
        assert resp.json()["total"] == 100
