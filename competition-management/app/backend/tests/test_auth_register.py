"""学生自助注册端点测试：角色边界、唯一性、自动登录。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest


def _payload(**overrides):
    data = {
        "email": "student@example.edu",
        "password": "MyPass123!",
        "name": "张三",
        "school": "浙江树人学院",
        "role": "CAPTAIN",
    }
    data.update(overrides)
    return data


async def test_register_captain_returns_token(client):
    r = await client.post("/api/auth/register", json=_payload())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["access_token"]
    assert body["user"]["role"] == "CAPTAIN"
    assert body["user"]["school"] == "浙江树人学院"
    assert body["user"]["can_review"] is False


async def test_register_then_login(client):
    assert (await client.post("/api/auth/register", json=_payload())).status_code == 201
    r = await client.post(
        "/api/auth/login",
        json={"email": "student@example.edu", "password": "MyPass123!"},
    )
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "student@example.edu"


async def test_register_token_works(client):
    token = (await client.post("/api/auth/register", json=_payload())).json()["access_token"]
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "student@example.edu"


async def test_register_duplicate_email(client):
    assert (await client.post("/api/auth/register", json=_payload())).status_code == 201
    r = await client.post("/api/auth/register", json=_payload())
    assert r.status_code == 409
    assert "已注册" in r.json()["detail"]


async def test_register_email_case_insensitive(client):
    await client.post("/api/auth/register", json=_payload())
    r = await client.post("/api/auth/register", json=_payload(email="STUDENT@EXAMPLE.EDU"))
    assert r.status_code == 409


@pytest.mark.parametrize("role", ["ADMIN", "JUDGE", "TEACHER"])
async def test_register_cannot_self_assign_privileged_role(client, role):
    r = await client.post("/api/auth/register", json=_payload(role=role))
    assert r.status_code == 422


async def test_register_default_role_is_captain(client):
    payload = _payload()
    del payload["role"]
    r = await client.post("/api/auth/register", json=payload)
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "CAPTAIN"


async def test_register_member_role(client):
    r = await client.post("/api/auth/register", json=_payload(email="member@example.edu", role="MEMBER"))
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "MEMBER"


@pytest.mark.parametrize(
    "payload",
    [
        _payload(password="123"),
        _payload(email="not-an-email"),
        _payload(name="x"),
        _payload(email="a@b"),
    ],
)
async def test_register_invalid_payload(client, payload):
    assert (await client.post("/api/auth/register", json=payload)).status_code == 422


async def test_registered_captain_can_create_team(client, admin_headers):
    token = (await client.post("/api/auth/register", json=_payload())).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    now = datetime.now(UTC)
    created = await client.post(
        "/api/competitions",
        json={
            "title": "注册测试赛事",
            "min_team_size": 1,
            "max_team_size": 3,
            "registration_opens_at": (now - timedelta(days=1)).isoformat(),
            "registration_closes_at": (now + timedelta(days=1)).isoformat(),
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    comp_id = created.json()["id"]
    tr = await client.post(
        f"/api/competitions/{comp_id}/transition",
        json={"target": "REGISTRATION_OPEN"},
        headers=admin_headers,
    )
    assert tr.status_code == 200, tr.text

    r = await client.post(
        "/api/teams",
        json={"competition_id": comp_id, "name": "注册测试队"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert any(
        m["user_id"] == r.json()["members"][0]["user_id"]
        and m["role_in_team"] == "CAPTAIN"
        for m in r.json()["members"]
    )


async def test_register_writes_audit_log(client, admin_headers):
    await client.post("/api/auth/register", json=_payload())
    r = await client.get("/api/audit", headers=admin_headers)
    assert r.status_code == 200
    assert any(row["action"] == "REGISTER" for row in r.json())
