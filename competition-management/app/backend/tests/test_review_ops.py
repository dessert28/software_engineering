"""FR-017 评审异常 / FR-018 评审复核接口测试。

先走通 P0 主链路（建赛事 → 报名 → 提交 → 分配 → 打分），再验证 P1：
异常延长/替换/回避、复核原始分数不可变与重复复核拦截。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from tests.conftest import login

ORIGINAL_DIMENSION = {"modeling": 88, "solving": 85, "writing": 90}
ORIGINAL_COMMENT = "模型假设清晰，求解过程完整，论文表述规范。"
# (88*40 + 85*40 + 90*20) / 100 = 87.2
ORIGINAL_TOTAL = 87.2


async def _create_competition(client, headers, **overrides) -> str:
    now = datetime.now(UTC)
    payload = {
        "title": "异常与复核测试竞赛",
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


async def _transition(client, headers, comp_id, target):
    resp = await client.post(
        f"/api/competitions/{comp_id}/transition",
        json={"target": target},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp


async def _prepare(client, admin_headers, captain_headers) -> tuple[str, str]:
    """推进到 REVIEWING 并建好已提交的作业，返回 (comp_id, submission_id)。"""
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
        json={
            "competition_id": comp_id,
            "name": "复核异常测试队",
            "school": "浙江树人学院",
        },
        headers=captain_headers,
    )
    assert team.status_code == 201, team.text
    enr = await client.post(
        "/api/enrollments",
        json={"competition_id": comp_id, "team_id": team.json()["id"]},
        headers=captain_headers,
    )
    assert enr.status_code == 201, enr.text
    enr_id = enr.json()["id"]
    approved = await client.post(
        f"/api/enrollments/{enr_id}/review",
        json={"status": "APPROVED"},
        headers=admin_headers,
    )
    assert approved.status_code == 200, approved.text

    for target in ("REGISTRATION_CLOSED", "QUALIFICATION_REVIEW", "RUNNING", "SUBMISSION_OPEN"):
        await _transition(client, admin_headers, comp_id, target)

    sub = await client.post(f"/api/submissions/by-enrollment/{enr_id}", headers=captain_headers)
    assert sub.status_code == 201, sub.text
    sub_id = sub.json()["id"]
    up = await client.post(
        f"/api/submissions/{sub_id}/versions",
        files={"file": ("paper.pdf", b"%PDF content", "application/pdf")},
        headers=captain_headers,
    )
    assert up.status_code == 201, up.text
    done = await client.post(f"/api/submissions/{sub_id}/submit", headers=captain_headers)
    assert done.status_code == 200, done.text

    for target in ("SUBMISSION_CLOSED", "REVIEWING"):
        await _transition(client, admin_headers, comp_id, target)

    return comp_id, sub_id


async def _judge_id(client, admin_headers, email: str) -> str:
    judges = (await client.get("/api/judges", headers=admin_headers)).json()
    return [j for j in judges if j["email"] == email][0]["id"]


async def _assign(
    client,
    admin_headers,
    comp_id: str,
    sub_id: str,
    reviewer_id: str,
    due_at=None,
) -> str:
    body = {
        "competition_id": comp_id,
        "submission_id": sub_id,
        "reviewer_id": reviewer_id,
    }
    if due_at is not None:
        body["due_at"] = due_at
    task = await client.post("/api/review-tasks", json=body, headers=admin_headers)
    assert task.status_code == 201, task.text
    return task.json()["id"]


async def _score(client, judge_headers, task_id: str):
    resp = await client.post(
        f"/api/review-tasks/{task_id}/score",
        json={"dimension": ORIGINAL_DIMENSION, "comment": ORIGINAL_COMMENT},
        headers=judge_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _task_due_at(client, admin_headers, comp_id: str, task_id: str):
    rows = (await client.get(
        f"/api/competitions/{comp_id}/review-tasks", headers=admin_headers
    )).json()
    return [t for t in rows if t["id"] == task_id][0]["due_at"]


class TestReviewExceptions:
    async def test_overdue_exception_then_resolve_extend(
        self, client, admin_headers, captain_headers, judge_headers, judge_id
    ):
        """标记逾期异常 → resolve 延长时间成功；重复处理应 409。"""
        comp_id, sub_id = await _prepare(client, admin_headers, captain_headers)
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        task_id = await _assign(client, admin_headers, comp_id, sub_id, judge_id, due_at=past)

        exc = await client.post(
            f"/api/review-tasks/{task_id}/exceptions",
            json={
                "exception_type": "OVERDUE",
                "reason": "专家逾期未提交评审结果，需要延期处理。",
            },
            headers=admin_headers,
        )
        assert exc.status_code == 201, exc.text
        body = exc.json()
        assert body["status"] == "OPEN"
        assert body["task_id"] == task_id
        assert body["created_by"] is not None

        before_due = await _task_due_at(client, admin_headers, comp_id, task_id)
        new_due = (datetime.now(UTC) + timedelta(days=7)).isoformat()
        resolved = await client.post(
            f"/api/review-exceptions/{body['id']}/resolve",
            json={
                "action": "EXTEND",
                "handling_note": "已与专家沟通，同意延长一周完成评审。",
                "due_at": new_due,
            },
            headers=admin_headers,
        )
        assert resolved.status_code == 200, resolved.text
        result = resolved.json()
        assert result["exception"]["status"] == "RESOLVED"
        assert result["exception"]["handled_by"] is not None
        assert result["new_task"] is None

        after_due = await _task_due_at(client, admin_headers, comp_id, task_id)
        assert after_due is not None and after_due != before_due

        # 已处理的异常不能重复处理
        again = await client.post(
            f"/api/review-exceptions/{body['id']}/resolve",
            json={"action": "MANUAL", "handling_note": "重复处理尝试。"},
            headers=admin_headers,
        )
        assert again.status_code == 409

        # 审计留痕
        logs = await client.get(
            "/api/audit",
            params={"object_id": body["id"], "action": "EXCEPTION"},
            headers=admin_headers,
        )
        assert logs.status_code == 200
        assert len(logs.json()) >= 1

    async def test_create_exception_with_extend_action_updates_task(
        self, client, admin_headers, captain_headers, judge_headers, judge_id
    ):
        """创建异常时直接带 EXTEND，应同时更新任务截止时间。"""
        comp_id, sub_id = await _prepare(client, admin_headers, captain_headers)
        task_id = await _assign(client, admin_headers, comp_id, sub_id, judge_id)
        before_due = await _task_due_at(client, admin_headers, comp_id, task_id)
        new_due = (datetime.now(UTC) + timedelta(days=5)).isoformat()

        resp = await client.post(
            f"/api/review-tasks/{task_id}/exceptions",
            json={
                "exception_type": "OVERDUE",
                "reason": "评审时间不足，直接申请延期。",
                "action": "EXTEND",
                "due_at": new_due,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["action"] == "EXTEND"
        assert await _task_due_at(client, admin_headers, comp_id, task_id) != before_due

        # EXTEND 缺 due_at → 400
        bad = await client.post(
            f"/api/review-tasks/{task_id}/exceptions",
            json={"exception_type": "OVERDUE", "reason": "缺少延期时间的异常记录。", "action": "EXTEND"},
            headers=admin_headers,
        )
        assert bad.status_code == 400

    async def test_replace_with_same_school_judge_blocked(
        self, client, admin_headers, captain_headers, judge_headers, judge_id
    ):
        """REPLACE 指定同校专家，应触发回避冲突 409。"""
        comp_id, sub_id = await _prepare(client, admin_headers, captain_headers)
        task_id = await _assign(client, admin_headers, comp_id, sub_id, judge_id)
        judge2_id = await _judge_id(client, admin_headers, "judge2@test.edu")

        exc = await client.post(
            f"/api/review-tasks/{task_id}/exceptions",
            json={"exception_type": "CONFLICT", "reason": "原专家申请回避本次评审任务。"},
            headers=admin_headers,
        )
        assert exc.status_code == 201, exc.text
        exc_id = exc.json()["id"]

        resp = await client.post(
            f"/api/review-exceptions/{exc_id}/resolve",
            json={
                "action": "REPLACE",
                "handling_note": "尝试替换为同校专家，应被回避规则拦截。",
                "replacement_reviewer_id": judge2_id,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 409, resp.text
        assert "回避" in resp.json()["detail"]

        # 拦截后异常仍为 OPEN，可再次处理
        rows = (await client.get(
            f"/api/competitions/{comp_id}/review-exceptions", headers=admin_headers
        )).json()
        assert [r for r in rows if r["id"] == exc_id][0]["status"] == "OPEN"

    async def test_replace_with_external_judge_succeeds(
        self, client, admin_headers, captain_headers, judge_headers, judge_id
    ):
        """REPLACE 指定外校新专家，成功创建新任务并把原任务标记为 REPLACED。"""
        comp_id, sub_id = await _prepare(client, admin_headers, captain_headers)
        task_id = await _assign(client, admin_headers, comp_id, sub_id, judge_id)

        new_judge = await client.post(
            "/api/judges",
            json={
                "email": "judge3@test.edu",
                "name": "外校专家三",
                "password": "Passw0rd!",
                "school": "外地大学",
            },
            headers=admin_headers,
        )
        assert new_judge.status_code == 201, new_judge.text
        judge3_id = new_judge.json()["id"]

        exc = await client.post(
            f"/api/review-tasks/{task_id}/exceptions",
            json={"exception_type": "REFUSAL", "reason": "原专家拒绝继续评审该作品。"},
            headers=admin_headers,
        )
        exc_id = exc.json()["id"]

        resolved = await client.post(
            f"/api/review-exceptions/{exc_id}/resolve",
            json={
                "action": "REPLACE",
                "handling_note": "改派外校专家继续评审。",
                "replacement_reviewer_id": judge3_id,
            },
            headers=admin_headers,
        )
        assert resolved.status_code == 200, resolved.text
        new_task = resolved.json()["new_task"]
        assert new_task is not None
        assert new_task["reviewer_id"] == judge3_id
        assert new_task["submission_id"] == sub_id
        assert new_task["status"] == "ASSIGNED"
        assert new_task["material_ref"]

        tasks = (await client.get(
            f"/api/competitions/{comp_id}/review-tasks", headers=admin_headers
        )).json()
        assert [t for t in tasks if t["id"] == task_id][0]["status"] == "REPLACED"

        # 同一专家重复分配应被拦截：另建一个异常再尝试替换给同一人
        dup = await client.post(
            f"/api/review-tasks/{new_task['id']}/exceptions",
            json={"exception_type": "OTHER", "reason": "用于验证重复分配拦截的异常。"},
            headers=admin_headers,
        )
        assert dup.status_code == 201
        dup_resolve = await client.post(
            f"/api/review-exceptions/{dup.json()['id']}/resolve",
            json={
                "action": "REPLACE",
                "handling_note": "重复指派同一专家。",
                "replacement_reviewer_id": judge3_id,
            },
            headers=admin_headers,
        )
        assert dup_resolve.status_code == 409

    async def test_non_admin_cannot_create_exception(self, client, judge_headers, captain_headers):
        """非管理员（专家/队长）不能标记评审异常。"""
        body = {
            "exception_type": "OVERDUE",
            "reason": "非管理员越权尝试标记评审异常。",
        }
        as_judge = await client.post(
            "/api/review-tasks/not-a-task/exceptions", json=body, headers=judge_headers
        )
        assert as_judge.status_code == 403
        as_captain = await client.post(
            "/api/review-tasks/not-a-task/exceptions", json=body, headers=captain_headers
        )
        assert as_captain.status_code == 403

    async def test_unknown_task_returns_404(self, client, admin_headers):
        resp = await client.post(
            "/api/review-tasks/does-not-exist/exceptions",
            json={"exception_type": "OVERDUE", "reason": "任务不存在时的异常标记。"},
            headers=admin_headers,
        )
        assert resp.status_code == 404


class TestRecheck:
    async def test_recheck_never_mutates_original_score(
        self, client, admin_headers, captain_headers, judge_headers, judge_id
    ):
        """创建复核后原始分数不进入复核结果；decide 后原 ScoreRecord 保持原值。"""
        comp_id, sub_id = await _prepare(client, admin_headers, captain_headers)
        task_id = await _assign(client, admin_headers, comp_id, sub_id, judge_id)
        score = await _score(client, judge_headers, task_id)
        assert score["total_score"] == ORIGINAL_TOTAL
        score_id = score["id"]

        recheck = await client.post(
            f"/api/competitions/{comp_id}/rechecks",
            json={"task_id": task_id, "reason": "参赛队申诉，需复核评分细节。"},
            headers=admin_headers,
        )
        assert recheck.status_code == 201, recheck.text
        assert recheck.json()["original_score_id"] == score_id
        assert recheck.json()["status"] == "PENDING"
        recheck_id = recheck.json()["id"]

        detail = await client.get(f"/api/rechecks/{recheck_id}", headers=admin_headers)
        assert detail.status_code == 200
        assert detail.json()["original"]["total_score"] == ORIGINAL_TOTAL
        assert detail.json()["original"]["comment"] == ORIGINAL_COMMENT
        frozen = json.loads(detail.json()["recheck"]["frozen_original_json"])
        assert frozen["total_score"] == ORIGINAL_TOTAL
        assert frozen["comment"] == ORIGINAL_COMMENT

        decided = await client.post(
            f"/api/rechecks/{recheck_id}/decide",
            json={
                "dimension": {"modeling": 95, "solving": 92, "writing": 88},
                "comment": "复核认为模型创新性被低估，按细则予以调分。",
            },
            headers=admin_headers,
        )
        assert decided.status_code == 200, decided.text
        assert decided.json()["status"] == "COMPLETED"
        # (95*40 + 92*40 + 88*20) / 100 = 92.4
        assert decided.json()["revised_total"] == 92.4

        # 原始 ScoreRecord 始终未被修改
        after = await client.get(f"/api/rechecks/{recheck_id}", headers=admin_headers)
        assert after.json()["original"]["id"] == score_id
        assert after.json()["original"]["total_score"] == ORIGINAL_TOTAL
        assert after.json()["original"]["comment"] == ORIGINAL_COMMENT
        assert after.json()["recheck"]["revised_total"] == 92.4

        # 复核动作写审计
        logs = await client.get(
            "/api/audit",
            params={"object_id": recheck_id, "action": "RECHECK"},
            headers=admin_headers,
        )
        assert len(logs.json()) >= 1

    async def test_duplicate_recheck_rejected(
        self, client, admin_headers, captain_headers, judge_headers, judge_id
    ):
        """同一最终评分重复发起复核应 409。"""
        comp_id, sub_id = await _prepare(client, admin_headers, captain_headers)
        task_id = await _assign(client, admin_headers, comp_id, sub_id, judge_id)
        await _score(client, judge_headers, task_id)

        payload = {"task_id": task_id, "reason": "针对该评分的复核申请。"}
        first = await client.post(
            f"/api/competitions/{comp_id}/rechecks", json=payload, headers=admin_headers
        )
        assert first.status_code == 201, first.text
        second = await client.post(
            f"/api/competitions/{comp_id}/rechecks", json=payload, headers=admin_headers
        )
        assert second.status_code == 409

    async def test_non_admin_cannot_create_recheck(self, client, judge_headers):
        resp = await client.post(
            "/api/competitions/whatever/rechecks",
            json={"task_id": "whatever", "reason": "非管理员越权发起复核。"},
            headers=judge_headers,
        )
        assert resp.status_code == 403

    async def test_unassigned_judge_cannot_decide(
        self, client, admin_headers, captain_headers, judge_headers, judge_id
    ):
        """未被指定的专家不能作出复核结论。"""
        comp_id, sub_id = await _prepare(client, admin_headers, captain_headers)
        task_id = await _assign(client, admin_headers, comp_id, sub_id, judge_id)
        await _score(client, judge_headers, task_id)

        recheck = await client.post(
            f"/api/competitions/{comp_id}/rechecks",
            json={"task_id": task_id, "reason": "测试未指派专家越权复核。"},
            headers=admin_headers,
        )
        recheck_id = recheck.json()["id"]
        judge2_headers = await login(client, "judge2@test.edu")
        resp = await client.post(
            f"/api/rechecks/{recheck_id}/decide",
            json={
                "dimension": {"modeling": 90, "solving": 90, "writing": 90},
                "comment": "未受指派专家尝试提交复核结论。",
            },
            headers=judge2_headers,
        )
        assert resp.status_code == 403

        # 被拒后仍为 PENDING，管理员可正常复核
        assert (await client.get(
            f"/api/rechecks/{recheck_id}", headers=admin_headers
        )).json()["recheck"]["status"] == "PENDING"

    async def test_decide_twice_rejected(
        self, client, admin_headers, captain_headers, judge_headers, judge_id
    ):
        """同一复核不能重复决定。"""
        comp_id, sub_id = await _prepare(client, admin_headers, captain_headers)
        task_id = await _assign(client, admin_headers, comp_id, sub_id, judge_id)
        await _score(client, judge_headers, task_id)
        recheck_id = (await client.post(
            f"/api/competitions/{comp_id}/rechecks",
            json={"task_id": task_id, "reason": "重复决定拦截测试。"},
            headers=admin_headers,
        )).json()["id"]

        body = {
            "dimension": {"modeling": 80, "solving": 80, "writing": 80},
            "comment": "第一次复核结论，内容完整清晰。",
        }
        assert (await client.post(
            f"/api/rechecks/{recheck_id}/decide", json=body, headers=admin_headers
        )).status_code == 200
        assert (await client.post(
            f"/api/rechecks/{recheck_id}/decide", json=body, headers=admin_headers
        )).status_code == 409
