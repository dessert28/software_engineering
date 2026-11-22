"""路由：认证。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AuditAction
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_session
from app.models import User
from app.schemas import LoginRequest, RegisterRequest, TokenOut, UserOut
from app.services import audit

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post(
    "/register", response_model=TokenOut, status_code=201, summary="学生自助注册（队长/队员）"
)
async def register(payload: RegisterRequest, session: AsyncSession = Depends(get_session)) -> TokenOut:
    """自助注册只开放 CAPTAIN / MEMBER 两种学生角色。

    管理员、评委、指导教师由平台管理员创建，不允许自助注册提权。
    邮箱全局唯一；注册成功即返回令牌，前端可直接进入系统。
    """
    exists = (
        await session.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "该邮箱已注册")

    user = User(
        email=payload.email,
        name=payload.name,
        role=payload.role,
        school=payload.school.strip() if payload.school else None,
        password_hash=hash_password(payload.password),
        can_review=False,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "该邮箱已注册") from None

    token = create_access_token(user.id, extra={"role": user.role})
    await audit.record(
        session, action=AuditAction.REGISTER, object_type="User", object_id=user.id, actor=user
    )
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut, summary="登录并获取访问令牌")
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenOut:
    user = (await session.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号或密码错误")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已停用")

    token = create_access_token(user.id, extra={"role": user.role})
    await audit.record(
        session, action=AuditAction.LOGIN, object_type="User", object_id=user.id, actor=user
    )
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut, summary="读取当前登录用户")
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
