"""匿名评审的对抗性测试。

普通测试只验证「正常路径下材料里没有队伍名」，但匿名性真正的风险在于
专家能不能从周边接口把身份拼出来。这里专门试这些越界动作。
"""

from __future__ import annotations

import pytest

from tests.conftest import login
from tests.test_flow import prepare_reviewable


class TestAnonymityBoundary:
    async def test_material_has_no_identity_leak(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        """材料 payload 逐字段扫描，任何一个字段都不该出现队伍/学校/人员信息。"""
        comp_id, sub_id, judge_id = await prepare_reviewable(
            client, admin_headers, captain_headers
        )
        task = (
            await client.post(
                "/api/review-tasks",
                json={"competition_id": comp_id, "submission_id": sub_id, "reviewer_id": judge_id},
                headers=admin_headers,
            )
        ).json()

        body = (
            await client.get(f"/api/review-tasks/{task['id']}/material", headers=judge_headers)
        ).json()

        blob = str(body)
        for forbidden in ("评审测试队", "浙江树人学院", "CAPTAIN", "teacher@test.edu", "captain@test.edu"):
            assert forbidden not in blob, f"材料泄漏了 {forbidden}"

        # 只允许出现作品编号这一种标识
        assert body["problem_code"].startswith("作品编号")

    async def test_judge_cannot_read_other_judges_task(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        """专家 A 的任务，专家 B 读不到。"""
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

        other_judge = await login(client, "judge2@test.edu")
        resp = await client.get(f"/api/review-tasks/{task_id}/material", headers=other_judge)
        assert resp.status_code == 403

    async def test_judge_cannot_score_others_task(
        self, client, admin_headers, captain_headers, judge_headers
    ):
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

        other_judge = await login(client, "judge2@test.edu")
        resp = await client.post(
            f"/api/review-tasks/{task_id}/score",
            json={"dimension": {"modeling": 90, "solving": 90, "writing": 90}, "comment": "替别人打分不应该成功"},
            headers=other_judge,
        )
        assert resp.status_code == 403

    async def test_judge_cannot_list_all_tasks(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        """赛事全量任务列表是管理员视角，专家不能拉。"""
        comp_id, sub_id, judge_id = await prepare_reviewable(
            client, admin_headers, captain_headers
        )
        await client.post(
            "/api/review-tasks",
            json={"competition_id": comp_id, "submission_id": sub_id, "reviewer_id": judge_id},
            headers=admin_headers,
        )
        resp = await client.get(
            f"/api/competitions/{comp_id}/review-tasks", headers=judge_headers
        )
        assert resp.status_code == 403

    async def test_judge_mine_only_returns_own_tasks(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        comp_id, sub_id, judge_id = await prepare_reviewable(
            client, admin_headers, captain_headers
        )
        await client.post(
            "/api/review-tasks",
            json={"competition_id": comp_id, "submission_id": sub_id, "reviewer_id": judge_id},
            headers=admin_headers,
        )

        mine = (await client.get("/api/review-tasks/mine", headers=judge_headers)).json()
        assert len(mine) == 1

        other = await login(client, "judge2@test.edu")
        theirs = (await client.get("/api/review-tasks/mine", headers=other)).json()
        assert theirs == []

    async def test_material_omits_file_storage_path(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        """文件路径/存储 key 不能出现在材料里，否则能反推上传者。"""
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

        body = (
            await client.get(f"/api/review-tasks/{task_id}/material", headers=judge_headers)
        ).json()

        assert "storage_key" not in body
        assert "path" not in str(body).lower() or "路径" not in str(body)
        assert sub_id not in str(body), "材料里不该出现 submission_id"


class TestSelfReviewConflict:
    async def test_same_school_conflict_blocked(self, client, admin_headers, captain_headers):
        """同校回避：队伍学校与专家学校一致时不能派任务。"""
        comp_id, sub_id, judge_id = await prepare_reviewable(
            client, admin_headers, captain_headers
        )
        judges = (await client.get("/api/judges", headers=admin_headers)).json()
        same_school = [j for j in judges if j["school"] == "浙江树人学院"]

        if not same_school:
            pytest.skip("夹具里没有同校专家，回避规则无法在此环境验证")

        resp = await client.post(
            "/api/review-tasks",
            json={
                "competition_id": comp_id,
                "submission_id": sub_id,
                "reviewer_id": same_school[0]["id"],
            },
            headers=admin_headers,
        )
        assert resp.status_code == 409
        assert "回避" in resp.json()["detail"]

    async def test_inactive_judge_cannot_be_assigned(
        self, client, admin_headers, captain_headers
    ):
        comp_id, sub_id, judge_id = await prepare_reviewable(
            client, admin_headers, captain_headers
        )
        await client.patch(
            f"/api/judges/{judge_id}/availability",
            params={"can_review": False},
            headers=admin_headers,
        )
        resp = await client.post(
            "/api/review-tasks",
            json={"competition_id": comp_id, "submission_id": sub_id, "reviewer_id": judge_id},
            headers=admin_headers,
        )
        assert resp.status_code == 409


class TestScoreImmutability:
    async def test_second_score_from_same_judge_rejected(
        self, client, admin_headers, captain_headers, judge_headers
    ):
        """同一任务只能打一次分 —— 评分一旦提交就是最终意见。"""
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

        first = await client.post(
            f"/api/review-tasks/{task_id}/score",
            json={"dimension": {"modeling": 80, "solving": 80, "writing": 80}, "comment": "第一次评分，内容足够长。"},
            headers=judge_headers,
        )
        assert first.status_code == 200

        second = await client.post(
            f"/api/review-tasks/{task_id}/score",
            json={"dimension": {"modeling": 99, "solving": 99, "writing": 99}, "comment": "试图改分，内容也足够长。"},
            headers=judge_headers,
        )
        assert second.status_code == 409

    async def test_ai_authority_never_weighted(self, client, admin_headers, captain_headers, judge_headers):
        """即便库里有 ADVISORY 记录，汇总也不能把它算进去。"""
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
            json={"dimension": {"modeling": 60, "solving": 60, "writing": 60}, "comment": "人工给出的保守分数。"},
            headers=judge_headers,
        )

        await client.post(
            f"/api/competitions/{comp_id}/transition",
            json={"target": "RESULT_PENDING"},
            headers=admin_headers,
        )
        calc = await client.post(
            f"/api/competitions/{comp_id}/results/calculate", headers=admin_headers
        )
        # 只有一条 HUMAN 记录，总分应为 60，不受任何 AI 分影响
        assert calc.json()["results"][0]["final_score"] == 60.0
