"""应用配置：从环境变量或 .env 读取，全部集中在这里，业务代码不直接碰 os.environ。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import (
    DEFAULT_AI_MODEL_ID,
    DEFAULT_AI_PROMPT_VERSION,
    DEFAULT_AI_RULE_VERSION,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "数学建模比赛管理系统"
    api_prefix: str = "/api"
    debug: bool = True

    database_url: str = "sqlite+aiosqlite:///./data/mmcm.db"

    secret_key: str = "dev-only-secret-change-me"
    access_token_expire_minutes: int = 480
    algorithm: str = "HS256"

    storage_backend: str = "local"
    storage_local_root: str = "./data/uploads"

    max_upload_bytes: int = 52_428_800
    allowed_upload_extensions: str = ".pdf,.docx,.doc,.zip,.rar,.7z,.xlsx,.csv,.py,.md,.txt"

    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    seed_on_startup: bool = True

    # ── AI 预评级（评审侧）──────────────────────────────────
    # heuristic 默认离线可跑；切 openai_compatible 需配 base_url/api_key/model_name。
    ai_provider: str = "heuristic"
    ai_model_id: str = DEFAULT_AI_MODEL_ID
    ai_prompt_version: str = DEFAULT_AI_PROMPT_VERSION
    ai_rule_version: str = DEFAULT_AI_RULE_VERSION
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model_name: str = ""
    ai_timeout_seconds: float = 30.0
    ai_max_concurrency: int = 2
    ai_daily_budget: int = 2000

    @property
    def allowed_extensions(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_upload_extensions.split(",") if e.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sqlite_path(self) -> Path | None:
        """SQLite 的库文件绝对路径；非 SQLite 返回 None。

        相对路径不能交给 SQLite 自己解析 —— 它按进程 CWD 算，换个启动目录就
        找不到文件（报「unable to open database file」）。统一在这里落到
        BACKEND_ROOT，保证从任何目录启动都指向同一个库。
        """
        if not self.is_sqlite:
            return None
        _, _, tail = self.database_url.partition(":///")
        if not tail or tail == ":memory:":
            return None
        p = Path(tail.split("?")[0])
        return p if p.is_absolute() else (BACKEND_ROOT / p)

    @property
    def resolved_database_url(self) -> str:
        """把 SQLite 相对路径替换为绝对路径后的连接串。"""
        p = self.sqlite_path
        if p is None:
            return self.database_url
        return f"sqlite+aiosqlite:///{p.as_posix()}"

    @property
    def storage_root(self) -> Path:
        p = Path(self.storage_local_root)
        return p if p.is_absolute() else (BACKEND_ROOT / p)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def ensure_dirs(self) -> None:
        """启动前把库目录和存储目录建好，避免首次运行就报错。"""
        p = self.sqlite_path
        if p is not None:
            p.parent.mkdir(parents=True, exist_ok=True)
        self.storage_root.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
