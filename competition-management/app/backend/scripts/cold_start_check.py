"""冷启动自检：模拟容器首次运行（目录全空、库不存在）。

验证四件事：
1. 嵌套目录能被自动创建；
2. 表能建出来；
3. 种子数据能写进去；
4. 用真实 HTTP 打一次登录和赛事列表。
"""

import asyncio
import os
import sys

sys.path.insert(0, ".")

_db = os.environ["DATABASE_URL"]
print(f"[0] DATABASE_URL = {_db}")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402


async def main() -> int:
    ok = True

    print(f"[1] 解析后的库路径 = {settings.sqlite_path}")
    print(f"[2] 存储根目录 = {settings.storage_root}")
    print(f"[3] 目录已存在？库目录={(settings.sqlite_path.parent.exists())} "
          f"存储目录={settings.storage_root.exists()}")
    if not settings.sqlite_path.parent.exists():
        print("    !! 库目录没被创建")
        ok = False
    if not settings.storage_root.exists():
        print("    !! 存储目录没被创建")
        ok = False

    # 走 lifespan（建表 + 种子）
    async with app.router.lifespan_context(app):
        from select import select as _sel  # noqa: F401

        from sqlalchemy import select

        from app.models import Competition, User

        async with SessionLocal() as s:
            users = (await s.execute(select(User))).scalars().all()
            comps = (await s.execute(select(Competition))).scalars().all()
            print(f"[4] 种子用户 {len(users)} 个，赛事 {len(comps)} 个")
            print(f"    用户名: {[u.email for u in users]}")
            if len(users) < 3:
                print("    !! 种子账号不足")
                ok = False
            if len(comps) < 1:
                print("    !! 种子赛事缺失")
                ok = False

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/api/health")
            print(f"[5] /api/health -> {r.status_code} {r.json()}")
            ok &= r.status_code == 200

            r = await c.post(
                "/api/auth/login",
                json={"email": "admin@example.edu", "password": "Passw0rd!"},
            )
            print(f"[6] 登录 -> {r.status_code} role={r.json().get('user', {}).get('role')}")
            ok &= r.status_code == 200

            tok = r.json()["access_token"]
            r = await c.get("/api/competitions", headers={"Authorization": f"Bearer {tok}"})
            print(f"[7] 赛事列表 -> {r.status_code} 条数={len(r.json())}")
            ok &= r.status_code == 200

            r = await c.get("/api/meta/rubric")
            body = r.json()
            print(f"[8] 评分细则 -> {r.status_code} 项数={len(body['items'])} 合计={body['total']}")
            ok &= body["total"] == 100

    print("\n结果:", "冷启动通过" if ok else "冷启动失败")
    return 0 if ok else 1


sys.exit(asyncio.run(main()))
