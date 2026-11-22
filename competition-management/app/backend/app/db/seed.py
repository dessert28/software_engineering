"""种子数据：首次启动时写入最小可运行数据集。"""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    RUBRIC_ITEMS,
    CompetitionState,
    Role,
)
from app.core.security import hash_password
from app.models import Competition, RuleProfile, User

DEFAULT_PASSWORD = "Passw0rd!"

SEED_USERS = [
    ("admin@example.edu", "赛事管理员", Role.ADMIN, "浙江树人学院"),
    ("teacher@example.edu", "李指导", Role.TEACHER, "浙江树人学院"),
    ("judge@example.edu", "王评审", Role.JUDGE, "外校评审中心"),
]


async def seed_if_empty(session: AsyncSession) -> dict[str, int]:
    created = {"users": 0, "competitions": 0, "rules": 0}

    for email, name, role, school in SEED_USERS:
        exists = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if exists:
            continue
        session.add(
            User(
                email=email,
                name=name,
                role=role.value,
                school=school,
                password_hash=hash_password(DEFAULT_PASSWORD),
            )
        )
        created["users"] += 1

    rule_count = (await session.execute(select(func.count()).select_from(RuleProfile))).scalar_one()
    rule: RuleProfile | None = None
    if rule_count == 0:
        rule = RuleProfile(
            name="校赛标准评分细则",
            version=1,
            rubric_json=json.dumps(
                {"items": RUBRIC_ITEMS, "trim_high": 0, "trim_low": 0}, ensure_ascii=False
            ),
            aggregation="MEAN",
        )
        session.add(rule)
        created["rules"] += 1
        await session.flush()

    comp_count = (await session.execute(select(func.count()).select_from(Competition))).scalar_one()
    if comp_count == 0:
        admin = (
            await session.execute(select(User).where(User.email == SEED_USERS[0][0]))
        ).scalar_one()
        comp = Competition(
            title="2026 年浙江树人学院数学建模竞赛",
            edition="2026 秋季",
            organizer="教务处",
            description="示例赛事，用于验证赛事主链路。",
            state=CompetitionState.REGISTRATION_OPEN.value,
            min_team_size=2,
            max_team_size=3,
            rule_profile_id=rule.id if rule else None,
            created_by=admin.id,
        )
        session.add(comp)
        created["competitions"] += 1

    await session.flush()
    return created
