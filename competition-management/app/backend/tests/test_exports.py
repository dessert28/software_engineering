"""FR-025 数据导出与赛事归档测试。

用 conftest 的 client/admin_headers/captain_headers；赛事数据直接用 SessionLocal
造，避免为了测导出先走完 8 步生命周期。
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Competition, CompetitionResult, Enrollment, Team


async def _create_competition(client, headers, **overrides) -> str:
    now = datetime.now(UTC)
    payload = {
        "title": "导出归档测试赛事",
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


async def _seed_data(comp_id: str, *, enrollment_count: int = 2, result_count: int = 1) -> None:
    """造 N 支队伍 + 对应报名，以及前 result_count 个成绩。"""
    async with SessionLocal() as session:
        for i in range(enrollment_count):
            team = Team(
                competition_id=comp_id,
                name=f"测试队伍{i + 1}",
                school="浙江树人学院",
            )
            session.add(team)
            await session.flush()
            session.add(
                Enrollment(competition_id=comp_id, team_id=team.id, status="APPROVED")
            )
            await session.flush()
            if i < result_count:
                session.add(
                    CompetitionResult(
                        competition_id=comp_id,
                        team_id=team.id,
                        team_name=team.name,
                        final_score=90.0 - i,
                        rank=i + 1,
                        status="PUBLISHED",
                    )
                )
        await session.commit()


async def _set_state(comp_id: str, state: str) -> None:
    async with SessionLocal() as session:
        comp = await session.get(Competition, comp_id)
        comp.state = state
        await session.commit()


async def _create_export(client, headers, comp_id: str, data_kind: str, export_format: str = "CSV"):
    return await client.post(
        f"/api/competitions/{comp_id}/exports",
        json={"data_kind": data_kind, "export_format": export_format},
        headers=headers,
    )


class TestExport:
    async def test_export_enrollments_csv_header_and_row_count(self, client, admin_headers):
        comp_id = await _create_competition(client, admin_headers)
        await _seed_data(comp_id, enrollment_count=2)

        resp = await _create_export(client, admin_headers, comp_id, "ENROLLMENTS", "CSV")
        assert resp.status_code == 200, resp.text
        summary = resp.json()
        assert summary["data_kind"] == "ENROLLMENTS"
        assert summary["row_count"] == 2
        assert summary["status"] == "COMPLETED"
        # 摘要不得回吐完整内容
        assert "content" not in summary

        download = await client.get(
            f"/api/exports/{summary['id']}/content", headers=admin_headers
        )
        assert download.status_code == 200
        rows = list(csv.reader(io.StringIO(download.text)))
        assert rows[0][0] == "id"
        assert "status" in rows[0]
        assert "team_id" in rows[0]
        assert len(rows) == 3  # 表头 + 2 条数据

    async def test_export_results_json_is_parseable(self, client, admin_headers):
        comp_id = await _create_competition(client, admin_headers)
        await _seed_data(comp_id, enrollment_count=2, result_count=2)

        resp = await _create_export(client, admin_headers, comp_id, "RESULTS", "JSON")
        assert resp.status_code == 200, resp.text
        assert resp.json()["row_count"] == 2

        download = await client.get(
            f"/api/exports/{resp.json()['id']}/content", headers=admin_headers
        )
        assert download.status_code == 200
        payload = json.loads(download.text)
        assert isinstance(payload, list)
        assert len(payload) == 2
        assert payload[0]["team_name"] == "测试队伍1"
        assert payload[0]["final_score"] == 90.0

    async def test_invalid_data_kind_rejected(self, client, admin_headers):
        comp_id = await _create_competition(client, admin_headers)
        resp = await _create_export(client, admin_headers, comp_id, "NOT_A_KIND")
        assert resp.status_code == 400

    async def test_invalid_export_format_rejected(self, client, admin_headers):
        comp_id = await _create_competition(client, admin_headers)
        resp = await _create_export(client, admin_headers, comp_id, "TEAMS", "PDF")
        assert resp.status_code == 400

    async def test_non_admin_cannot_export(self, client, captain_headers, admin_headers):
        comp_id = await _create_competition(client, admin_headers)
        resp = await _create_export(client, captain_headers, comp_id, "ENROLLMENTS")
        assert resp.status_code == 403

    async def test_list_exports_returns_summaries_only(self, client, admin_headers):
        comp_id = await _create_competition(client, admin_headers)
        await _seed_data(comp_id)
        await _create_export(client, admin_headers, comp_id, "ENROLLMENTS")
        await _create_export(client, admin_headers, comp_id, "TEAMS")

        resp = await client.get(
            f"/api/competitions/{comp_id}/exports", headers=admin_headers
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 2
        assert {r["data_kind"] for r in rows} == {"ENROLLMENTS", "TEAMS"}
        assert all("content" not in r for r in rows)

    async def test_download_media_types(self, client, admin_headers):
        comp_id = await _create_competition(client, admin_headers)
        await _seed_data(comp_id)

        csv_resp = await _create_export(client, admin_headers, comp_id, "ENROLLMENTS", "CSV")
        csv_download = await client.get(
            f"/api/exports/{csv_resp.json()['id']}/content", headers=admin_headers
        )
        assert csv_download.headers["content-type"] == "text/csv; charset=utf-8"

        json_resp = await _create_export(client, admin_headers, comp_id, "RESULTS", "JSON")
        json_download = await client.get(
            f"/api/exports/{json_resp.json()['id']}/content", headers=admin_headers
        )
        assert json_download.headers["content-type"] == "application/json"

    async def test_non_admin_cannot_download(self, client, admin_headers, captain_headers):
        comp_id = await _create_competition(client, admin_headers)
        export_id = (
            await _create_export(client, admin_headers, comp_id, "ENROLLMENTS")
        ).json()["id"]
        resp = await client.get(f"/api/exports/{export_id}/content", headers=captain_headers)
        assert resp.status_code == 403

    async def test_download_missing_returns_404(self, client, admin_headers):
        resp = await client.get("/api/exports/no-such-export/content", headers=admin_headers)
        assert resp.status_code == 404


class TestArchive:
    async def test_force_archive_requires_note_from_draft(self, client, admin_headers):
        comp_id = await _create_competition(client, admin_headers)

        denied = await client.post(
            f"/api/competitions/{comp_id}/archive", json={}, headers=admin_headers
        )
        assert denied.status_code == 400

        short = await client.post(
            f"/api/competitions/{comp_id}/archive",
            json={"note": "取消"},
            headers=admin_headers,
        )
        assert short.status_code == 400

        ok = await client.post(
            f"/api/competitions/{comp_id}/archive",
            json={"note": "赛事取消不再举办"},
            headers=admin_headers,
        )
        assert ok.status_code == 200, ok.text
        record = ok.json()
        assert record["competition_id"] == comp_id
        assert record["note"] == "赛事取消不再举办"
        assert record["snapshot_key"].startswith(f"archive/{comp_id}/")
        assert record["snapshot_key"].endswith(".json")

        comp = await client.get(f"/api/competitions/{comp_id}", headers=admin_headers)
        assert comp.json()["state"] == "ARCHIVED"

        records = await client.get(f"/api/competitions/{comp_id}/archive", headers=admin_headers)
        assert len(records.json()) == 1
        assert records.json()[0]["id"] == record["id"]

    async def test_archive_from_appeal_succeeds_without_note(self, client, admin_headers):
        comp_id = await _create_competition(client, admin_headers)
        await _set_state(comp_id, "APPEAL")

        resp = await client.post(
            f"/api/competitions/{comp_id}/archive", json={}, headers=admin_headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["note"] is None

        comp = await client.get(f"/api/competitions/{comp_id}", headers=admin_headers)
        assert comp.json()["state"] == "ARCHIVED"

    async def test_archive_from_illegal_state_conflicts(self, client, admin_headers):
        comp_id = await _create_competition(client, admin_headers)
        await _set_state(comp_id, "REVIEWING")

        resp = await client.post(
            f"/api/competitions/{comp_id}/archive",
            json={"note": "强制作废该赛事"},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    async def test_any_logged_in_user_can_read_archives(self, client, admin_headers, captain_headers):
        comp_id = await _create_competition(client, admin_headers)
        await client.post(
            f"/api/competitions/{comp_id}/archive",
            json={"note": "赛事取消不再举办"},
            headers=admin_headers,
        )
        resp = await client.get(f"/api/competitions/{comp_id}/archive", headers=captain_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_archive_writes_audit_log(self, client, admin_headers):
        comp_id = await _create_competition(client, admin_headers)
        await client.post(
            f"/api/competitions/{comp_id}/archive",
            json={"note": "赛事取消不再举办"},
            headers=admin_headers,
        )
        logs = await client.get(
            "/api/audit",
            params={"object_id": comp_id, "action": "ARCHIVE"},
            headers=admin_headers,
        )
        assert logs.status_code == 200
        assert len(logs.json()) == 1
        assert logs.json()[0]["reason"] == "赛事取消不再举办"
