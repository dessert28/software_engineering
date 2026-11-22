"""FR-027 团队协作空间 + FR-028 版本复审跟踪端到端测试。

每个用例从干净夹具出发，按真实链路铺垫：
建赛事 → 开放报名 → 建两支队伍 → 加成员 → 报名审核 → 推到提交开放
→ 建提交 → 上传版本，然后再验证协作备注与复审相关端点。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.conftest import login


async def _create_competition(client, admin_headers, **overrides) -> str:
    now = datetime.now(UTC)
    payload = {
        "title": "协作复审测试竞赛",
        "edition": "2026 测试",
        "min_team_size": 1,
        "max_team_size": 3,
        "registration_opens_at": (now - timedelta(days=1)).isoformat(),
        "registration_closes_at": (now + timedelta(days=1)).isoformat(),
        "submission_opens_at": (now - timedelta(hours=1)).isoformat(),
        "submission_closes_at": (now + timedelta(days=2)).isoformat(),
    }
    payload.update(overrides)
    resp = await client.post("/api/competitions", json=payload, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _transition(client, headers, comp_id, target):
    return await client.post(
        f"/api/competitions/{comp_id}/transition", json={"target": target}, headers=headers
    )


async def _setup(client, admin_headers, captain_headers) -> dict:
    """铺垫出一届赛事、两支队伍及各自的提交版本。"""
    member_headers = await login(client, "member@test.edu")
    comp_id = await _create_competition(client, admin_headers)

    resp = await _transition(client, admin_headers, comp_id, "REGISTRATION_OPEN")
    assert resp.status_code == 200, resp.text

    # 甲队：captain 创建，自动成为队长；member 加入为普通队员
    team_a = await client.post(
        "/api/teams",
        json={"competition_id": comp_id, "name": "协作测试甲队"},
        headers=captain_headers,
    )
    assert team_a.status_code == 201, team_a.text
    team_a_id = team_a.json()["id"]
    added = await client.post(
        f"/api/teams/{team_a_id}/members",
        json={"email": "member@test.edu", "role_in_team": "MEMBER"},
        headers=captain_headers,
    )
    assert added.status_code == 200, added.text

    # 乙队：member 创建，自动成为乙队队长（用于越权场景）
    team_b = await client.post(
        "/api/teams",
        json={"competition_id": comp_id, "name": "协作测试乙队"},
        headers=member_headers,
    )
    assert team_b.status_code == 201, team_b.text
    team_b_id = team_b.json()["id"]

    # 报名并审核通过
    enr_a = await client.post(
        "/api/enrollments",
        json={"competition_id": comp_id, "team_id": team_a_id},
        headers=captain_headers,
    )
    assert enr_a.status_code == 201, enr_a.text
    enr_b = await client.post(
        "/api/enrollments",
        json={"competition_id": comp_id, "team_id": team_b_id},
        headers=member_headers,
    )
    assert enr_b.status_code == 201, enr_b.text
    for enr_id in (enr_a.json()["id"], enr_b.json()["id"]):
        reviewed = await client.post(
            f"/api/enrollments/{enr_id}/review",
            json={"status": "APPROVED"},
            headers=admin_headers,
        )
        assert reviewed.status_code == 200, reviewed.text

    for target in ("REGISTRATION_CLOSED", "QUALIFICATION_REVIEW", "RUNNING", "SUBMISSION_OPEN"):
        resp = await _transition(client, admin_headers, comp_id, target)
        assert resp.status_code == 200, f"{target}: {resp.text}"

    sub_a = await client.post(
        f"/api/submissions/by-enrollment/{enr_a.json()['id']}", headers=captain_headers
    )
    assert sub_a.status_code == 201, sub_a.text
    sub_b = await client.post(
        f"/api/submissions/by-enrollment/{enr_b.json()['id']}", headers=member_headers
    )
    assert sub_b.status_code == 201, sub_b.text

    up_a = await client.post(
        f"/api/submissions/{sub_a.json()['id']}/versions",
        files={"file": ("a.pdf", b"content-of-a", "application/pdf")},
        headers=captain_headers,
    )
    assert up_a.status_code == 201, up_a.text
    up_b = await client.post(
        f"/api/submissions/{sub_b.json()['id']}/versions",
        files={"file": ("b.pdf", b"content-of-b", "application/pdf")},
        headers=member_headers,
    )
    assert up_b.status_code == 201, up_b.text

    return {
        "comp_id": comp_id,
        "team_a_id": team_a_id,
        "team_b_id": team_b_id,
        "sub_a": sub_a.json()["id"],
        "sub_b": sub_b.json()["id"],
        "version_a": up_a.json()["id"],
        "version_b": up_b.json()["id"],
        "member_headers": member_headers,
    }


async def _create_review(client, ctx, headers, **overrides) -> str:
    body = {
        "team_id": ctx["team_a_id"],
        "submission_id": ctx["sub_a"],
        "version_id": ctx["version_a"],
        "summary": "请复核模型假设与求解过程",
    }
    body.update(overrides)
    resp = await client.post(
        f"/api/competitions/{ctx['comp_id']}/revision-reviews", json=body, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestCollaborationNotes:
    async def test_captain_writes_note(self, client, admin_headers, captain_headers):
        ctx = await _setup(client, admin_headers, captain_headers)
        captain = (await client.get("/api/auth/me", headers=captain_headers)).json()

        resp = await client.post(
            f"/api/teams/{ctx['team_a_id']}/notes",
            json={"content": "第一次讨论：先确认指标权重"},
            headers=captain_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["team_id"] == ctx["team_a_id"]
        assert body["author_id"] == captain["id"]
        assert body["content"] == "第一次讨论：先确认指标权重"
        assert body["created_at"] and body["updated_at"]

    async def test_non_member_judge_cannot_write_note(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        ctx = await _setup(client, admin_headers, captain_headers)
        resp = await client.post(
            f"/api/teams/{ctx['team_a_id']}/notes",
            json={"content": "越权备注"},
            headers=judge_headers,
        )
        assert resp.status_code == 403

    async def test_member_can_read_notes(self, client, admin_headers, captain_headers):
        ctx = await _setup(client, admin_headers, captain_headers)
        created = await client.post(
            f"/api/teams/{ctx['team_a_id']}/notes",
            json={"content": "队员可见的协作记录"},
            headers=captain_headers,
        )
        assert created.status_code == 201, created.text

        resp = await client.get(
            f"/api/teams/{ctx['team_a_id']}/notes", headers=ctx["member_headers"]
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()) == 1
        assert resp.json()[0]["content"] == "队员可见的协作记录"

    async def test_note_requires_nonempty_content(self, client, admin_headers, captain_headers):
        ctx = await _setup(client, admin_headers, captain_headers)
        resp = await client.post(
            f"/api/teams/{ctx['team_a_id']}/notes", json={"content": ""}, headers=captain_headers
        )
        assert resp.status_code == 422

    async def test_note_on_missing_team_returns_404(self, client, admin_headers, captain_headers):
        resp = await client.post(
            "/api/teams/not-exist-team/notes",
            json={"content": "发给不存在的队伍"},
            headers=captain_headers,
        )
        assert resp.status_code == 404


class TestRevisionReviews:
    async def test_create_review_starts_open(self, client, admin_headers, captain_headers):
        ctx = await _setup(client, admin_headers, captain_headers)
        captain = (await client.get("/api/auth/me", headers=captain_headers)).json()

        resp = await client.post(
            f"/api/competitions/{ctx['comp_id']}/revision-reviews",
            json={
                "team_id": ctx["team_a_id"],
                "submission_id": ctx["sub_a"],
                "version_id": ctx["version_a"],
                "summary": "复审意见摘要",
            },
            headers=captain_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "OPEN"
        assert body["competition_id"] == ctx["comp_id"]
        assert body["team_id"] == ctx["team_a_id"]
        assert body["version_id"] == ctx["version_a"]
        assert body["raised_by"] == captain["id"]
        assert body["summary"] == "复审意见摘要"

    async def test_add_issue_then_detail_shows_it(self, client, admin_headers, captain_headers):
        ctx = await _setup(client, admin_headers, captain_headers)
        review_id = await _create_review(client, ctx, captain_headers)

        created = await client.post(
            f"/api/revision-reviews/{review_id}/issues",
            json={"description": "模型假设与题设条件矛盾，请复核"},
            headers=captain_headers,
        )
        assert created.status_code == 201, created.text
        assert created.json()["status"] == "OPEN"
        issue_id = created.json()["id"]

        detail = await client.get(
            f"/api/revision-reviews/{review_id}", headers=captain_headers
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["review"]["id"] == review_id
        issues = detail.json()["issues"]
        assert [i["id"] for i in issues] == [issue_id]
        assert issues[0]["description"] == "模型假设与题设条件矛盾，请复核"

    async def test_resolve_without_note_rejected(self, client, admin_headers, captain_headers):
        ctx = await _setup(client, admin_headers, captain_headers)
        review_id = await _create_review(client, ctx, captain_headers)
        issue_id = (
            await client.post(
                f"/api/revision-reviews/{review_id}/issues",
                json={"description": "求解过程缺少灵敏度分析"},
                headers=captain_headers,
            )
        ).json()["id"]

        resp = await client.patch(
            f"/api/revision-issues/{issue_id}",
            json={"status": "RESOLVED"},
            headers=captain_headers,
        )
        assert resp.status_code in (400, 422), resp.text

        unchanged = await client.get(
            f"/api/revision-reviews/{review_id}", headers=captain_headers
        )
        assert unchanged.json()["issues"][0]["status"] == "OPEN"

    async def test_resolve_with_note_updates_status(
        self, client, admin_headers, captain_headers
    ):
        ctx = await _setup(client, admin_headers, captain_headers)
        review_id = await _create_review(client, ctx, captain_headers)
        issue_id = (
            await client.post(
                f"/api/revision-reviews/{review_id}/issues",
                json={"description": "论文表达需补充符号说明"},
                headers=captain_headers,
            )
        ).json()["id"]

        resp = await client.patch(
            f"/api/revision-issues/{issue_id}",
            json={
                "status": "RESOLVED",
                "resolution_note": "已在修改稿中补充符号说明表。",
                "version_id": ctx["version_a"],
            },
            headers=captain_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "RESOLVED"
        assert body["resolution_note"] == "已在修改稿中补充符号说明表。"
        assert body["version_id"] == ctx["version_a"]
        assert body["handled_by"]

    async def test_version_not_belonging_to_submission_rejected(
        self, client, admin_headers, captain_headers
    ):
        ctx = await _setup(client, admin_headers, captain_headers)
        resp = await client.post(
            f"/api/competitions/{ctx['comp_id']}/revision-reviews",
            json={
                "team_id": ctx["team_a_id"],
                "submission_id": ctx["sub_a"],
                "version_id": ctx["version_b"],  # 属于乙队的 submission
            },
            headers=captain_headers,
        )
        assert resp.status_code == 400, resp.text

    async def test_other_team_captain_cannot_read_review(
        self, client, admin_headers, captain_headers
    ):
        ctx = await _setup(client, admin_headers, captain_headers)
        # 乙队成员以乙队队长身份发起复审，甲队队长不得读取
        review_id = await _create_review(
            client,
            ctx,
            ctx["member_headers"],
            team_id=ctx["team_b_id"],
            submission_id=ctx["sub_b"],
            version_id=ctx["version_b"],
        )
        resp = await client.get(
            f"/api/revision-reviews/{review_id}", headers=captain_headers
        )
        assert resp.status_code == 403

    async def test_judge_cannot_create_review(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        ctx = await _setup(client, admin_headers, captain_headers)
        resp = await client.post(
            f"/api/competitions/{ctx['comp_id']}/revision-reviews",
            json={
                "team_id": ctx["team_a_id"],
                "submission_id": ctx["sub_a"],
                "version_id": ctx["version_a"],
            },
            headers=judge_headers,
        )
        assert resp.status_code == 403

    async def test_list_reviews_scoped_by_team_and_status(
        self, client, admin_headers, captain_headers
    ):
        ctx = await _setup(client, admin_headers, captain_headers)
        await _create_review(client, ctx, captain_headers)
        await _create_review(
            client,
            ctx,
            ctx["member_headers"],
            team_id=ctx["team_b_id"],
            submission_id=ctx["sub_b"],
            version_id=ctx["version_b"],
        )

        as_admin = await client.get(
            f"/api/competitions/{ctx['comp_id']}/revision-reviews", headers=admin_headers
        )
        assert as_admin.status_code == 200, as_admin.text
        assert len(as_admin.json()) == 2

        as_captain = await client.get(
            f"/api/competitions/{ctx['comp_id']}/revision-reviews", headers=captain_headers
        )
        assert as_captain.status_code == 200, as_captain.text
        assert len(as_captain.json()) == 1
        assert as_captain.json()[0]["team_id"] == ctx["team_a_id"]

        opened = await client.get(
            f"/api/competitions/{ctx['comp_id']}/revision-reviews",
            params={"status": "OPEN"},
            headers=captain_headers,
        )
        assert len(opened.json()) == 1
        resolved = await client.get(
            f"/api/competitions/{ctx['comp_id']}/revision-reviews",
            params={"status": "COMPLETED"},
            headers=captain_headers,
        )
        assert resolved.json() == []
