"""测试夹具：内存 SQLite + 独立上传目录，每个用例都是干净环境。"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# 让 tests 能 import app
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# 环境变量必须在 import app.* 之前设好
_TMP = tempfile.mkdtemp(prefix="mmcm-test-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{Path(_TMP) / 'test.db'}"
os.environ["STORAGE_LOCAL_ROOT"] = str(Path(_TMP) / "uploads")
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only"
os.environ["SEED_ON_STARTUP"] = "true"
os.environ["MAX_UPLOAD_BYTES"] = "1048576"

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Competition, Enrollment, Submission, Team, User  # noqa: E402

PASSWORD = "Passw0rd!"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # 建基础账号
    async with SessionLocal() as session:
        users = [
            ("admin@test.edu", "管理员", "ADMIN", "浙江树人学院"),
            ("judge@test.edu", "外校专家", "JUDGE", "某某大学"),
            ("judge2@test.edu", "同校专家", "JUDGE", "浙江树人学院"),
            ("captain@test.edu", "队长", "CAPTAIN", "浙江树人学院"),
            ("member@test.edu", "队员", "MEMBER", "浙江树人学院"),
        ]
        for email, name, role, school in users:
            session.add(
                User(
                    email=email,
                    name=name,
                    role=role,
                    school=school,
                    password_hash=hash_password(PASSWORD),
                )
            )
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def login(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient) -> dict[str, str]:
    return await login(client, "admin@test.edu")


@pytest_asyncio.fixture
async def judge_headers(client: AsyncClient) -> dict[str, str]:
    return await login(client, "judge@test.edu")


@pytest_asyncio.fixture
async def captain_headers(client: AsyncClient) -> dict[str, str]:
    return await login(client, "captain@test.edu")


@pytest_asyncio.fixture
async def judge_id(client: AsyncClient, admin_headers: dict[str, str]) -> str:
    resp = await client.get("/api/judges", headers=admin_headers)
    rows = [u for u in resp.json() if u["email"] == "judge@test.edu"]
    assert rows, "找不到测试用评审专家"
    return rows[0]["id"]


@pytest_asyncio.fixture
async def user_id(client: AsyncClient, admin_headers: dict[str, str]) -> str:
    async with SessionLocal() as session:
        from sqlalchemy import select

        u = (await session.execute(select(User).where(User.email == "member@test.edu"))).scalar_one()
        return u.id
