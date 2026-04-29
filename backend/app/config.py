"""Application settings: env vars, merged dotenv files, and typed defaults."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/ root (parent of app/)


def _discover_app_env() -> str:
    """APP_ENV: shell / process env 优先，其次从根 .env 里读取，默认 dev。"""
    v = os.environ.get("APP_ENV", "").strip()
    if v:
        return v
    base = _BACKEND_DIR / ".env"
    if not base.is_file():
        return "dev"
    try:
        for raw in base.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if line.upper().startswith("APP_ENV="):
                return line.split("=", 1)[1].strip().strip("'\"") or "dev"
    except OSError:
        return "dev"
    return "dev"


def _env_file_paths() -> tuple[str, ...] | None:
    """多环境：先 .env 共享配置，再 .env.<APP_ENV> 覆盖（文件存在才加载）。"""
    app_env = _discover_app_env()
    out: list[str] = []
    for name in (".env", f".env.{app_env}"):
        p = _BACKEND_DIR / name
        if p.is_file():
            out.append(str(p))
    return tuple(out) or None


_APP_ENV = _discover_app_env()


class Settings(BaseSettings):
    """Pydantic-settings model for database URLs, JWT, AI timeouts, and feature flags."""

    model_config = SettingsConfigDict(
        env_file=_env_file_paths(),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    app_name: str = "minerva-api"
    app_env: str = Field(
        default=_APP_ENV,
        description="运行环境名。优先通过环境变量 APP_ENV 或根 .env 中的 APP_ENV 选择要合并的 .env.<name> 文件。",
        validation_alias=AliasChoices("APP_ENV", "app_env"),
    )
    database_url: str = Field(
        default="postgresql+asyncpg://minerva:minerva@127.0.0.1:5432/minerva",
        description="Async SQLAlchemy URL (asyncpg driver).",
    )
    sync_database_url: str = Field(
        default="postgresql+psycopg2://minerva:minerva@127.0.0.1:5432/minerva",
        description="Sync URL for Alembic and scripts (psycopg2).",
    )
    jwt_secret: str = Field(
        default="change_me_dev_only_32_bytes_minimum_please",
    )
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 7
    bcrypt_rounds: int = 12
    auto_create_tables: bool = Field(
        default=True,
        description="为 True 时启动时按 ORM 元数据补建缺表；生产建议 False 并仅用 Alembic。",
        validation_alias=AliasChoices("AUTO_CREATE_TABLES", "auto_create_tables"),
    )
    ai_http_connect_timeout: float = Field(
        default=10.0,
        description="AI 上游 HTTP 连接超时（秒）。",
        validation_alias=AliasChoices("AI_HTTP_CONNECT_TIMEOUT", "ai_http_connect_timeout"),
    )
    ai_http_read_timeout: float = Field(
        default=120.0,
        description="AI 上游 HTTP 读超时（秒）。",
        validation_alias=AliasChoices("AI_HTTP_READ_TIMEOUT", "ai_http_read_timeout"),
    )
    ai_retry_max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="可重试错误（超时、连接失败、429、503）的最大尝试次数。",
        validation_alias=AliasChoices("AI_RETRY_MAX_ATTEMPTS", "ai_retry_max_attempts"),
    )


# Singleton loaded at import time for ``from app.config import settings``.
settings = Settings()
