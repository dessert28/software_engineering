"""FR-029~031 AI 预评级 / 确定性分流路由测试。

造数直接用 SessionLocal（参考 test_statistics.py），避免完整走赛事状态机；
文本版本通过 storage.put_bytes 落盘后建 BlobObject + SubmissionVersion，
保证 L1 能提取正文、命中风险标记并进入 L2 成功路径。
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.core.constants import (
    EnrollmentStatus,
    ReviewTaskStatus,
    ScoreAuthority,
    SubmissionStatus,
)
from app.db.session import SessionLocal
from app.models import (
    BlobObject,
    Competition,
    Enrollment,
    ReviewTask,
    ScoreRecord,
    Submission,
    SubmissionVersion,
    Team,
    User,
)
from app.services.storage import get_storage


def _paper_text() -> str:
    """300+ 字符可提取正文；无图表编号、无公式，必然命中 FEW_FIGURES 进入 L2。"""
    return (
        "摘要：本文针对城市交通流量预测问题，提出一种基于时间序列分析的组合预测模型，"
        "首先对原始采集数据进行清洗、缺失值填补与归一化处理，然后利用滑动窗口方法构造训练样本集。"
        "模型部分结合线性回归与残差修正策略，在保证计算效率的同时显著提升了预测精度。"
        "求解阶段采用梯度下降算法对参数进行迭代优化，并通过交叉验证确定最优超参数组合。"
        "结果分析表明，本方法在多个独立测试集上的平均绝对误差明显低于基线模型，"
        "具有良好的泛化能力与鲁棒性，能够适应不同城市道路网络的复杂场景。"
        "结论部分总结了本文的主要贡献，并指出后续可以从数据维度扩展与模型结构改进两个方向继续深入研究。"
    )


async def _make_blob(session, text: str, suffix: str) -> BlobObject:
    storage_key = f"ai-test-{uuid.uuid4().hex}-{suffix}.md"
    md5, size = get_storage().put_bytes(storage_key, text.encode("utf-8"))
    blob = BlobObject(
        md5=md5,
        size_bytes=size,
        storage_key=storage_key,
        original_name="paper.md",
        mime_type="text/markdown",
        ref_count=1,
    )
    session.add(blob)
    await session.flush()
    return blob


@pytest_asyncio.fixture
async def ai_data(client: AsyncClient) -> dict[str, str]:
    """1 赛事 / 1 队伍 / 1 已提交作品（带文本版本）/ 2 名评审任务与相差 20 分的终稿评分。"""
    async with SessionLocal() as session:
        comp = Competition(title="AI 预评级测试赛事", state="DRAFT")
        session.add(comp)
        await session.flush()

        team = Team(name="AI 测试一队", competition_id=comp.id)
        session.add(team)
        await session.flush()

        enr = Enrollment(
            competition_id=comp.id,
            team_id=team.id,
            status=EnrollmentStatus.APPROVED.value,
        )
        session.add(enr)
        await session.flush()

        # 引擎若补齐了 Submission.competition_id 冗余列，造数也一并写入以兼容两种实现
        sub_kwargs: dict[str, object] = {
            "enrollment_id": enr.id,
            "status": SubmissionStatus.SUBMITTED.value,
        }
        if hasattr(Submission, "competition_id"):
            sub_kwargs["competition_id"] = comp.id
        sub = Submission(**sub_kwargs)
        session.add(sub)
        await session.flush()

        blob = await _make_blob(session, _paper_text(), "v1")
        version = SubmissionVersion(
            submission_id=sub.id, version_no=1, blob_id=blob.id, note="初稿"
        )
        session.add(version)
        await session.flush()
        sub.current_version_id = version.id
        await session.flush()

        judge = (
            await session.execute(select(User).where(User.email == "judge@test.edu"))
        ).scalar_one()
        judge2 = (
            await session.execute(select(User).where(User.email == "judge2@test.edu"))
        ).scalar_one()

        task = ReviewTask(
            competition_id=comp.id,
            submission_id=sub.id,
            reviewer_id=judge.id,
            material_ref="ai-task-judge",
            status=ReviewTaskStatus.SUBMITTED.value,
        )
        other_task = ReviewTask(
            competition_id=comp.id,
            submission_id=sub.id,
            reviewer_id=judge2.id,
            material_ref="ai-task-judge2",
            status=ReviewTaskStatus.SUBMITTED.value,
        )
        session.add_all([task, other_task])
        await session.flush()

        session.add_all(
            [
                ScoreRecord(
                    task_id=task.id,
                    reviewer_id=judge.id,
                    dimension_json='{"modeling":90,"solving":90,"writing":90}',
                    total_score=90.0,
                    comment="模型完整，求解过程清晰，予以高分",
                    authority=ScoreAuthority.HUMAN.value,
                    is_final=True,
                ),
                ScoreRecord(
                    task_id=other_task.id,
                    reviewer_id=judge2.id,
                    dimension_json='{"modeling":70,"solving":70,"writing":70}',
                    total_score=70.0,
                    comment="结构尚可，细节仍需补充完善",
                    authority=ScoreAuthority.HUMAN.value,
                    is_final=True,
                ),
            ]
        )
        await session.commit()
        return {
            "competition_id": comp.id,
            "submission_id": sub.id,
            "version_id": version.id,
            "task_id": task.id,
            "other_task_id": other_task.id,
        }


# ───────────────────── 1. 批量评估 ─────────────────────
async def test_batch_assess_and_idempotent(
    client: AsyncClient,
    admin_headers: dict[str, str],
    ai_data: dict[str, str],
) -> None:
    url = f"/api/competitions/{ai_data['competition_id']}/ai/assess"

    first = await client.post(url, headers=admin_headers)
    assert first.status_code == 200, first.text
    summary = first.json()
    assert summary["total"] >= 1
    assert summary["succeeded"] >= 1
    assert summary["succeeded"] + summary["skipped"] + summary["failed"] == summary["total"]
    assert summary["records"], "应返回本次涉及的 AI 留档"
    assert all(r["authority"] == "ADVISORY" for r in summary["records"])
    assert all(r["version_id"] == ai_data["version_id"] for r in summary["records"])

    listed = await client.get(
        f"/api/competitions/{ai_data['competition_id']}/ai/assessments",
        headers=admin_headers,
    )
    assert listed.status_code == 200, listed.text
    count = len(listed.json())
    assert count >= 1

    # 重复评估：幂等复用，记录数不增加
    again = await client.post(url, headers=admin_headers)
    assert again.status_code == 200, again.text
    listed_again = await client.get(
        f"/api/competitions/{ai_data['competition_id']}/ai/assessments",
        headers=admin_headers,
    )
    assert len(listed_again.json()) == count


async def test_batch_assess_empty_competition(
    client: AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    async with SessionLocal() as session:
        comp = Competition(title="空赛事", state="DRAFT")
        session.add(comp)
        await session.commit()
        cid = comp.id

    resp = await client.post(f"/api/competitions/{cid}/ai/assess", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["total"] == 0 and d["records"] == []


async def test_batch_assess_forbidden_for_captain(
    client: AsyncClient,
    captain_headers: dict[str, str],
    ai_data: dict[str, str],
) -> None:
    resp = await client.post(
        f"/api/competitions/{ai_data['competition_id']}/ai/assess",
        headers=captain_headers,
    )
    assert resp.status_code == 403


# ───────────────────── 2. 单作品评估 ─────────────────────
async def test_single_assessment_returns_score(
    client: AsyncClient,
    admin_headers: dict[str, str],
    ai_data: dict[str, str],
) -> None:
    resp = await client.post(
        f"/api/submissions/{ai_data['submission_id']}/ai-assessment",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["version_id"] == ai_data["version_id"]
    assert d["suggested_score"] is not None
    assert d["evaluation_level"] == "L2"
    assert d["status"] == "SUCCEEDED"
    assert d["authority"] == "ADVISORY"
    assert d["confidence"] is not None
    assert d["risk_flags"], "L1 应至少标记一个风险信号"


async def test_single_assessment_rejects_foreign_version(
    client: AsyncClient,
    admin_headers: dict[str, str],
    ai_data: dict[str, str],
) -> None:
    async with SessionLocal() as session:
        sub = Competition(title="另一赛事", state="DRAFT")
        session.add(sub)
        await session.flush()
        team = Team(name="另一队伍", competition_id=sub.id)
        session.add(team)
        await session.flush()
        enr = Enrollment(competition_id=sub.id, team_id=team.id)
        session.add(enr)
        await session.flush()
        kwargs: dict[str, object] = {"enrollment_id": enr.id}
        if hasattr(Submission, "competition_id"):
            kwargs["competition_id"] = sub.id
        other = Submission(**kwargs)
        session.add(other)
        await session.flush()
        blob = await _make_blob(session, _paper_text() + "\n补充说明：此为另一作品的独立正文。", "foreign")
        version = SubmissionVersion(
            submission_id=other.id, version_no=1, blob_id=blob.id
        )
        session.add(version)
        await session.commit()
        vid = version.id

    resp = await client.post(
        f"/api/submissions/{ai_data['submission_id']}/ai-assessment",
        params={"version_id": vid},
        headers=admin_headers,
    )
    assert resp.status_code == 400


# ───────────────────── 3. 专家端防锚定 ─────────────────────
async def test_judge_risk_flags_never_expose_score(
    client: AsyncClient,
    judge_headers: dict[str, str],
    admin_headers: dict[str, str],
    ai_data: dict[str, str],
) -> None:
    url = f"/api/review-tasks/{ai_data['task_id']}/ai-risk-flags"

    # 无 AI 记录时按纯人工流程提示
    before = await client.get(url, headers=judge_headers)
    assert before.status_code == 200, before.text
    assert before.json()["status"] == "NONE"
    assert before.json()["risk_flags"] == []
    assert before.json()["notice"] == "无 AI 参考，按人工评审流程进行"

    assess = await client.post(
        f"/api/submissions/{ai_data['submission_id']}/ai-assessment",
        headers=admin_headers,
    )
    assert assess.status_code == 200, assess.text

    after = await client.get(url, headers=judge_headers)
    assert after.status_code == 200, after.text
    body = after.json()
    # 防锚定纪律：以下三个字段及其字样绝对不能出现在专家端响应里
    text = after.text
    for banned in ("suggested_score", "confidence", "dimension_json"):
        assert banned not in body
        assert banned not in text
    assert body["task_id"] == ai_data["task_id"]
    assert body["status"] == "SUCCEEDED"
    assert len(body["risk_flags"]) >= 1
    assert all(set(flag) == {"code", "detail"} for flag in body["risk_flags"])


async def test_risk_flags_forbidden_for_other_judge_and_captain(
    client: AsyncClient,
    judge_headers: dict[str, str],
    captain_headers: dict[str, str],
    ai_data: dict[str, str],
) -> None:
    # 非本人任务
    other = await client.get(
        f"/api/review-tasks/{ai_data['other_task_id']}/ai-risk-flags",
        headers=judge_headers,
    )
    assert other.status_code == 403
    # 非评审角色
    captain = await client.get(
        f"/api/review-tasks/{ai_data['task_id']}/ai-risk-flags",
        headers=captain_headers,
    )
    assert captain.status_code == 403


# ───────────────────── 4. 确定性分流 ─────────────────────
async def test_escalation_score_gap_and_idempotent(
    client: AsyncClient,
    admin_headers: dict[str, str],
    ai_data: dict[str, str],
) -> None:
    url = f"/api/competitions/{ai_data['competition_id']}/ai/escalations/evaluate"

    first = await client.post(url, headers=admin_headers)
    assert first.status_code == 200, first.text
    codes = [row["rule_code"] for row in first.json()]
    assert "SCORE_GAP" in codes
    gap_row = next(row for row in first.json() if row["rule_code"] == "SCORE_GAP")
    assert gap_row["status"] == "OPEN"
    assert gap_row["submission_id"] == ai_data["submission_id"]
    assert gap_row["observed"]["gap"] == 20.0
    assert gap_row["thresholds"]["score_gap"] == 15.0

    # 同一作品同一规则只触发一次
    second = await client.post(url, headers=admin_headers)
    assert second.status_code == 200, second.text
    assert second.json() == []

    listed = await client.get(
        f"/api/competitions/{ai_data['competition_id']}/ai/escalations",
        headers=admin_headers,
    )
    assert listed.status_code == 200, listed.text
    assert any(row["rule_code"] == "SCORE_GAP" for row in listed.json())


async def test_handle_escalation_then_conflict(
    client: AsyncClient,
    admin_headers: dict[str, str],
    captain_headers: dict[str, str],
    ai_data: dict[str, str],
) -> None:
    evaluated = await client.post(
        f"/api/competitions/{ai_data['competition_id']}/ai/escalations/evaluate",
        headers=admin_headers,
    )
    assert evaluated.status_code == 200, evaluated.text
    row = next(r for r in evaluated.json() if r["rule_code"] == "SCORE_GAP")
    eid = row["id"]

    forbidden = await client.patch(
        f"/api/ai/escalations/{eid}",
        json={"status": "RESOLVED", "note": "由队长误操作"},
        headers=captain_headers,
    )
    assert forbidden.status_code == 403

    bad = await client.patch(
        f"/api/ai/escalations/{eid}",
        json={"status": "RESOLVED", "note": "短"},
        headers=admin_headers,
    )
    assert bad.status_code == 422

    ok = await client.patch(
        f"/api/ai/escalations/{eid}",
        json={"status": "RESOLVED", "note": "已追加第三位专家盲评"},
        headers=admin_headers,
    )
    assert ok.status_code == 200, ok.text
    d = ok.json()
    assert d["status"] == "RESOLVED"
    assert d["note"] == "已追加第三位专家盲评"
    assert d["handled_at"]

    conflict = await client.patch(
        f"/api/ai/escalations/{eid}",
        json={"status": "DISMISSED", "note": "重复处理请求"},
        headers=admin_headers,
    )
    assert conflict.status_code == 409

    filtered = await client.get(
        f"/api/competitions/{ai_data['competition_id']}/ai/escalations",
        params={"status": "RESOLVED"},
        headers=admin_headers,
    )
    assert filtered.status_code == 200, filtered.text
    assert [r["id"] for r in filtered.json()] == [eid]


# ───────────────────── 5. 状态过滤与 404 ─────────────────────
async def test_status_filters(
    client: AsyncClient,
    admin_headers: dict[str, str],
    ai_data: dict[str, str],
) -> None:
    assess_url = f"/api/competitions/{ai_data['competition_id']}/ai/assess"
    assert (await client.post(assess_url, headers=admin_headers)).status_code == 200
    listing = f"/api/competitions/{ai_data['competition_id']}/ai/assessments"

    succeeded = await client.get(listing, params={"status": "SUCCEEDED"}, headers=admin_headers)
    assert succeeded.status_code == 200, succeeded.text
    assert len(succeeded.json()) >= 1
    assert all(r["status"] == "SUCCEEDED" for r in succeeded.json())

    skipped = await client.get(listing, params={"status": "SKIPPED"}, headers=admin_headers)
    assert skipped.status_code == 200, skipped.text
    assert skipped.json() == []

    invalid = await client.get(listing, params={"status": "NOT_A_STATUS"}, headers=admin_headers)
    assert invalid.status_code == 422


async def test_missing_competition_returns_404(
    client: AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    cid = "competition-that-does-not-exist"
    assert (await client.post(f"/api/competitions/{cid}/ai/assess", headers=admin_headers)).status_code == 404
    assert (await client.get(f"/api/competitions/{cid}/ai/assessments", headers=admin_headers)).status_code == 404
    assert (await client.post(f"/api/competitions/{cid}/ai/escalations/evaluate", headers=admin_headers)).status_code == 404
    assert (await client.get(f"/api/competitions/{cid}/ai/escalations", headers=admin_headers)).status_code == 404


async def test_missing_task_and_escalation_returns_404(
    client: AsyncClient,
    judge_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    resp = await client.get(
        "/api/review-tasks/no-such-task/ai-risk-flags", headers=judge_headers
    )
    assert resp.status_code == 404
    patch = await client.patch(
        "/api/ai/escalations/no-such-escalation",
        json={"status": "RESOLVED", "note": "不存在的记录"},
        headers=admin_headers,
    )
    assert patch.status_code == 404
