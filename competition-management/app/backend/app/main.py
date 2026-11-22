"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.session import Base, SessionLocal, engine
from app.routers import ai_assessments as ai_assessments_router
from app.routers import appeals as appeals_router
from app.routers import audit as audit_router
from app.routers import auth as auth_router
from app.routers import collaboration as collaboration_router
from app.routers import competitions as competitions_router
from app.routers import exports as exports_router
from app.routers import notifications as notifications_router
from app.routers import results as results_router
from app.routers import review_ops as review_ops_router
from app.routers import reviews as reviews_router
from app.routers import statistics as statistics_router
from app.routers import submissions as submissions_router
from app.routers import teams as teams_router

logger = logging.getLogger("mmcm")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 建表。生产环境改 Alembic 迁移，初版用 create_all 快速起步。
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if settings.seed_on_startup:
        from app.db.seed import seed_if_empty

        async with SessionLocal() as session:
            created = await seed_if_empty(session)
            await session.commit()
        logger.info("种子数据：%s", created)

    # 健康自检：确认表结构可用
    logger.info("应用启动完成，环境=%s", "debug" if settings.debug else "release")
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "数学建模比赛管理系统初版 API。\n\n"
        "覆盖赛事主链路：建赛事 → 报名 → 审核 → 提交 → 评审 → 汇总 → 发布。\n"
        "AI 预评级只做路由参考（ADVISORY，永不进加权），复审触发由确定性规则产生。"
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (
    auth_router,
    competitions_router,
    teams_router,
    submissions_router,
    reviews_router,
    results_router,
    audit_router,
    # P1/P2 新增模块
    notifications_router,
    review_ops_router,
    appeals_router,
    exports_router,
    statistics_router,
    collaboration_router,
    ai_assessments_router,
):
    app.include_router(module.router, prefix=settings.api_prefix)


@app.get("/api/health", tags=["运维"], summary="健康检查")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": "0.1.0",
        "database": "sqlite" if settings.is_sqlite else "postgresql",
        "storage": settings.storage_backend,
    }


@app.get("/api/meta/lifecycle", tags=["运维"], summary="赛事生命周期元数据")
async def lifecycle() -> dict[str, object]:
    """前端渲染状态机图用：状态列表 + 合法迁移表。"""
    from app.core.constants import STATE_TRANSITIONS, CompetitionState

    return {
        "states": [s.value for s in CompetitionState],
        "transitions": {
            k.value: sorted(v.value for v in vals) for k, vals in STATE_TRANSITIONS.items()
        },
    }


@app.get("/api/meta/rubric", tags=["运维"], summary="默认评分细则")
async def rubric() -> dict[str, object]:
    from app.core.constants import RUBRIC_ITEMS

    return {"items": RUBRIC_ITEMS, "total": sum(int(i["weight"]) for i in RUBRIC_ITEMS)}
