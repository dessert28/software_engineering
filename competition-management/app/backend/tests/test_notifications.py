"""测试：站内通知中心（FR-005）。"""

from __future__ import annotations

from tests.conftest import login


async def _broadcast(client, headers, role="CAPTAIN", **overrides):
    body = {
        "target_role": role,
        "title": "测试通知标题",
        "body": "这是一条测试通知正文",
    }
    body.update(overrides)
    return await client.post("/api/notifications", json=body, headers=headers)


async def _my_id(client, headers) -> str:
    return (await client.get("/api/auth/me", headers=headers)).json()["id"]


class TestSendNotification:
    async def test_admin_broadcast_captain_receives(self, client, admin_headers, captain_headers):
        resp = await _broadcast(client, admin_headers)
        assert resp.status_code == 201, resp.text
        created = resp.json()
        assert len(created) == 1
        assert created[0]["target_role"] == "CAPTAIN"
        assert created[0]["recipient_id"] is None
        assert created[0]["status"] == "SENT"
        assert created[0]["channel"] == "IN_APP"

        mine = await client.get("/api/notifications/mine", headers=captain_headers)
        assert mine.status_code == 200
        assert len(mine.json()) == 1
        assert mine.json()[0]["title"] == "测试通知标题"

        count = await client.get("/api/notifications/mine/unread-count", headers=captain_headers)
        assert count.status_code == 200
        assert count.json() == {"count": 1}

    async def test_direct_recipient(self, client, admin_headers, captain_headers):
        captain_id = await _my_id(client, captain_headers)
        resp = await client.post(
            "/api/notifications",
            json={
                "recipient_id": captain_id,
                "title": "指定收件人通知",
                "body": "只有队长能看到",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()[0]["recipient_id"] == captain_id
        assert resp.json()[0]["target_role"] is None

        mine = await client.get("/api/notifications/mine", headers=captain_headers)
        assert len(mine.json()) == 1

    async def test_non_admin_cannot_create(self, client, captain_headers):
        resp = await _broadcast(client, captain_headers)
        assert resp.status_code == 403

    async def test_requires_recipient_or_role(self, client, admin_headers):
        resp = await client.post(
            "/api/notifications",
            json={"title": "无收件人通知", "body": "正文"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    async def test_unknown_recipient_returns_404(self, client, admin_headers):
        resp = await client.post(
            "/api/notifications",
            json={"recipient_id": "not-exist", "title": "指定收件人通知", "body": "正文"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    async def test_send_writes_audit_log(self, client, admin_headers):
        await _broadcast(client, admin_headers)
        logs = await client.get(
            "/api/audit", params={"action": "NOTIFY"}, headers=admin_headers
        )
        assert logs.status_code == 200
        assert len(logs.json()) == 1


class TestReadNotification:
    async def test_mark_read_clears_unread_and_is_idempotent(
        self, client, admin_headers, captain_headers
    ):
        await _broadcast(client, admin_headers)
        nid = (await client.get("/api/notifications/mine", headers=captain_headers)).json()[0]["id"]

        done = await client.post(f"/api/notifications/{nid}/read", headers=captain_headers)
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "READ"
        assert done.json()["read_by"] is not None
        assert done.json()["read_at"] is not None

        count = await client.get("/api/notifications/mine/unread-count", headers=captain_headers)
        assert count.json() == {"count": 0}

        again = await client.post(f"/api/notifications/{nid}/read", headers=captain_headers)
        assert again.status_code == 200
        assert again.json()["status"] == "READ"

    async def test_unread_only_filter(self, client, admin_headers, captain_headers):
        await _broadcast(client, admin_headers, title="第一条通知")
        await _broadcast(client, admin_headers, title="第二条通知")
        mine = (await client.get("/api/notifications/mine", headers=captain_headers)).json()
        assert len(mine) == 2

        first = mine[-1]["id"]
        await client.post(f"/api/notifications/{first}/read", headers=captain_headers)

        unread = await client.get(
            "/api/notifications/mine", params={"unread_only": "true"}, headers=captain_headers
        )
        assert unread.status_code == 200
        assert len(unread.json()) == 1
        assert unread.json()[0]["id"] != first

    async def test_other_user_cannot_mark_my_notification_read(
        self, client, admin_headers, captain_headers
    ):
        captain_id = await _my_id(client, captain_headers)
        made = await client.post(
            "/api/notifications",
            json={"recipient_id": captain_id, "title": "私密通知", "body": "仅队长可读"},
            headers=admin_headers,
        )
        nid = made.json()[0]["id"]

        member_headers = await login(client, "member@test.edu")
        resp = await client.post(f"/api/notifications/{nid}/read", headers=member_headers)
        assert resp.status_code == 403

    async def test_missing_notification_returns_404(self, client, captain_headers):
        resp = await client.post(
            "/api/notifications/no-such-id/read", headers=captain_headers
        )
        assert resp.status_code == 404


class TestAdminList:
    async def test_list_all_and_filters(self, client, admin_headers):
        await _broadcast(client, admin_headers, role="CAPTAIN", title="给队长的通知")
        await _broadcast(client, admin_headers, role="JUDGE", title="给专家的通知")

        all_rows = await client.get("/api/notifications", headers=admin_headers)
        assert all_rows.status_code == 200
        # 队长 1 人 + 专家 2 人（judge / judge2）
        assert len(all_rows.json()) == 3

        captains = await client.get(
            "/api/notifications", params={"role": "CAPTAIN"}, headers=admin_headers
        )
        assert len(captains.json()) == 1
        assert captains.json()[0]["title"] == "给队长的通知"

        judges = await client.get(
            "/api/notifications", params={"role": "JUDGE"}, headers=admin_headers
        )
        assert len(judges.json()) == 2

    async def test_non_admin_cannot_list_all(self, client, captain_headers):
        resp = await client.get("/api/notifications", headers=captain_headers)
        assert resp.status_code == 403
