"""FastAPI 依赖：当前用户、角色校验、数据库会话。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import Role
from app.core.security import decode_token
from app.db.session import get_session
from app.models import User

bearer = HTTPBearer(auto_error=False)

# 谁能进入评审流程。只有这两类角色 —— 匿名评审的价值建立在这个集合不扩张之上。
PRIVILEGED_REVIEW_ROLES: frozenset[Role] = frozenset({Role.ADMIN, Role.JUDGE})


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "缺少访问令牌")
    payload = decode_token(creds.credentials)
    if not payload or not payload.get("sub"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌无效或已过期")
    user = await session.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号不存在或已停用")
    return user


def require_roles(*roles: Role) -> Callable[[User], Awaitable[User]]:
    allowed = {r.value for r in roles}

    async def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "当前角色无权执行此操作")
        return user

    return _dep


def require_admin() -> Callable[[User], Awaitable[User]]:
    return require_roles(Role.ADMIN)
