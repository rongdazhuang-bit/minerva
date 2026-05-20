"""Application settings: env vars, single dotenv file per profile, typed defaults."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/ root (parent of app/)


def _discover_app_env() -> str:
    """APP_ENV: 进程环境变量优先；未设置时默认 local（对应 .env.local）。"""
    v = os.environ.get("APP_ENV", "").strip()
    return v or "local"


def _env_file_paths() -> tuple[str, ...] | None:
    """单环境：仅加载 backend/.env.<APP_ENV>（文件存在才加载）。"""
    app_env = _discover_app_env()
    path = _BACKEND_DIR / f".env.{app_env}"
    return (str(path),) if path.is_file() else None


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
        description=(
            "运行环境 profile 名。启动脚本在调用 Python 前设置 APP_ENV；"
            "仅加载 backend/.env.<profile> 单个文件（无叠加）。"
        ),
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
    jwt_access_ttl_minutes: int = 60
    jwt_refresh_ttl_days: int = 7
    bcrypt_rounds: int = 12
    auth_login_captcha_enabled: bool = Field(
        default=True,
        description="为 True 时 POST /auth/login 与 /auth/register 须携带有效图形验证码。",
        validation_alias=AliasChoices(
            "AUTH_LOGIN_CAPTCHA_ENABLED",
            "auth_login_captcha_enabled",
        ),
    )
    auth_login_captcha_ttl_seconds: int = Field(
        default=300,
        ge=60,
        le=900,
        description="登录验证码在 Redis 中的存活秒数。",
        validation_alias=AliasChoices(
            "AUTH_LOGIN_CAPTCHA_TTL_SECONDS",
            "auth_login_captcha_ttl_seconds",
        ),
    )
    auth_login_captcha_length: int = Field(
        default=4,
        ge=4,
        le=6,
        description="登录验证码字符个数（大写字母与数字）。",
        validation_alias=AliasChoices(
            "AUTH_LOGIN_CAPTCHA_LENGTH",
            "auth_login_captcha_length",
        ),
    )
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
    celery_broker_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        description="Celery broker URL for task enqueue operations.",
        validation_alias=AliasChoices("CELERY_BROKER_URL", "celery_broker_url"),
    )
    celery_result_backend: str = Field(
        default="redis://127.0.0.1:6379/1",
        description="Celery backend URL for task states/results.",
        validation_alias=AliasChoices("CELERY_RESULT_BACKEND", "celery_result_backend"),
    )
    celery_default_queue: str = Field(
        default="default",
        description="Default queue name for run-now dispatch.",
        validation_alias=AliasChoices("CELERY_DEFAULT_QUEUE", "celery_default_queue"),
    )
    celery_schedule_sync_channel: str = Field(
        default="minerva:celery:schedule_sync",
        description="Redis pub/sub channel for celery beat hot-reload events.",
        validation_alias=AliasChoices(
            "CELERY_SCHEDULE_SYNC_CHANNEL",
            "celery_schedule_sync_channel",
        ),
    )
    celery_schedule_reconcile_seconds: int = Field(
        default=60,
        ge=10,
        le=3600,
        description="Low-frequency reconciliation interval hint for beat sync.",
        validation_alias=AliasChoices(
            "CELERY_SCHEDULE_RECONCILE_SECONDS",
            "celery_schedule_reconcile_seconds",
        ),
    )
    celery_beat_hot_reload_via_redis: bool = Field(
        default=True,
        description=(
            "When True, celery beat subscribes to celery_schedule_sync_channel and "
            "reloads Postgres schedules promptly after CRUD/start/stop events."
        ),
        validation_alias=AliasChoices(
            "CELERY_BEAT_HOT_RELOAD_VIA_REDIS",
            "celery_beat_hot_reload_via_redis",
        ),
    )
    celery_beat_max_loop_seconds: int = Field(
        default=8,
        ge=1,
        le=120,
        description=(
            "Upper bound seconds celery beat sleeps between ticks when idle; "
            "keeps UI-driven schedule changes observable even if Redis events are delayed."
        ),
        validation_alias=AliasChoices(
            "CELERY_BEAT_MAX_LOOP_SECONDS",
            "celery_beat_max_loop_seconds",
        ),
    )
    agent_max_plan_steps: int = Field(
        default=8,
        ge=1,
        description="Planner 单次 run 最大计划步数。",
        validation_alias=AliasChoices("AGENT_MAX_PLAN_STEPS", "agent_max_plan_steps"),
    )
    agent_subagent_recursion_limit: int = Field(
        default=16,
        ge=1,
        description="子 Agent create_react_agent 的 recursion_limit。",
        validation_alias=AliasChoices(
            "AGENT_SUBAGENT_RECURSION_LIMIT",
            "agent_subagent_recursion_limit",
        ),
    )
    agent_memory_retrieve_limit: int = Field(
        default=20,
        ge=1,
        description="长期记忆检索最大条数。",
        validation_alias=AliasChoices(
            "AGENT_MEMORY_RETRIEVE_LIMIT",
            "agent_memory_retrieve_limit",
        ),
    )
    agent_message_fallback_limit: int = Field(
        default=50,
        ge=1,
        description="长期记忆不足时 agent_message fallback 条数。",
        validation_alias=AliasChoices(
            "AGENT_MESSAGE_FALLBACK_LIMIT",
            "agent_message_fallback_limit",
        ),
    )
    agent_chat_history_message_limit: int = Field(
        default=40,
        ge=1,
        description="单次 run 注入模型的会话历史最大消息条数（按 seq 截断保留最近）。",
        validation_alias=AliasChoices(
            "AGENT_CHAT_HISTORY_MESSAGE_LIMIT",
            "agent_chat_history_message_limit",
        ),
    )
    agent_langgraph_checkpoint_enabled: bool = Field(
        default=True,
        description="为 True 时尝试启用 LangGraph PostgresSaver checkpoint。",
        validation_alias=AliasChoices(
            "AGENT_LANGGRAPH_CHECKPOINT_ENABLED",
            "agent_langgraph_checkpoint_enabled",
        ),
    )
    agent_langgraph_checkpoint_pool_min_size: int = Field(
        default=1,
        ge=1,
        le=32,
        description="LangGraph checkpoint 专用 psycopg 连接池最小连接数。",
        validation_alias=AliasChoices(
            "AGENT_LANGGRAPH_CHECKPOINT_POOL_MIN_SIZE",
            "agent_langgraph_checkpoint_pool_min_size",
        ),
    )
    agent_langgraph_checkpoint_pool_max_size: int = Field(
        default=8,
        ge=1,
        le=64,
        description="LangGraph checkpoint 专用 psycopg 连接池最大连接数。",
        validation_alias=AliasChoices(
            "AGENT_LANGGRAPH_CHECKPOINT_POOL_MAX_SIZE",
            "agent_langgraph_checkpoint_pool_max_size",
        ),
    )
    agent_langgraph_checkpoint_pool_timeout: float = Field(
        default=60.0,
        ge=5.0,
        le=300.0,
        description="从 checkpoint 连接池获取连接的超时时间（秒）。",
        validation_alias=AliasChoices(
            "AGENT_LANGGRAPH_CHECKPOINT_POOL_TIMEOUT",
            "agent_langgraph_checkpoint_pool_timeout",
        ),
    )
    agent_langgraph_checkpoint_retention_days: int = Field(
        default=7,
        ge=1,
        le=3650,
        description="LangGraph checkpoint 行保留天数（按 create_at 清理）。",
        validation_alias=AliasChoices(
            "AGENT_LANGGRAPH_CHECKPOINT_RETENTION_DAYS",
            "agent_langgraph_checkpoint_retention_days",
        ),
    )
    agent_langgraph_checkpoint_cleanup_enabled: bool = Field(
        default=True,
        description="为 False 时 agent.checkpoint_purge 任务直接跳过。",
        validation_alias=AliasChoices(
            "AGENT_LANGGRAPH_CHECKPOINT_CLEANUP_ENABLED",
            "agent_langgraph_checkpoint_cleanup_enabled",
        ),
    )
    agent_langgraph_checkpoint_cleanup_batch_size: int = Field(
        default=1000,
        ge=1,
        le=50_000,
        description="checkpoint 清理每表每轮 DELETE 行数上限。",
        validation_alias=AliasChoices(
            "AGENT_LANGGRAPH_CHECKPOINT_CLEANUP_BATCH_SIZE",
            "agent_langgraph_checkpoint_cleanup_batch_size",
        ),
    )
    agent_files_root: str = Field(
        default="",
        description="Agent 工作区文件沙箱根目录；空则使用 backend/data/agent-files。",
        validation_alias=AliasChoices("AGENT_FILES_ROOT", "agent_files_root"),
    )
    agent_file_max_bytes: int = Field(
        default=524288,
        ge=1024,
        description="Agent file 技能单文件读/写最大字节数。",
        validation_alias=AliasChoices("AGENT_FILE_MAX_BYTES", "agent_file_max_bytes"),
    )
    doc_translate_max_file_bytes: int = Field(
        default=20971520,
        ge=1024,
        description="文档翻译单文件最大字节数（默认 20MB）。",
        validation_alias=AliasChoices(
            "DOC_TRANSLATE_MAX_FILE_BYTES",
            "doc_translate_max_file_bytes",
        ),
    )
    doc_translate_segment_concurrency: int = Field(
        default=5,
        ge=1,
        le=20,
        description="文档翻译段落并发调用模型数。",
        validation_alias=AliasChoices(
            "DOC_TRANSLATE_SEGMENT_CONCURRENCY",
            "doc_translate_segment_concurrency",
        ),
    )
    doc_translate_ocr_poll_interval_seconds: float = Field(
        default=2.0,
        ge=0.5,
        le=60.0,
        description="扫描 PDF 等待 OCR 轮询间隔（秒）。",
        validation_alias=AliasChoices(
            "DOC_TRANSLATE_OCR_POLL_INTERVAL_SECONDS",
            "doc_translate_ocr_poll_interval_seconds",
        ),
    )
    doc_translate_ocr_timeout_seconds: int = Field(
        default=1800,
        ge=60,
        le=7200,
        description="扫描 PDF 等待 OCR 最大秒数。",
        validation_alias=AliasChoices(
            "DOC_TRANSLATE_OCR_TIMEOUT_SECONDS",
            "doc_translate_ocr_timeout_seconds",
        ),
    )
    doc_translate_default_ocr_type: str = Field(
        default="PADDLE_OCR",
        description="扫描 PDF 自动 OCR 使用的 ocr_type。",
        validation_alias=AliasChoices(
            "DOC_TRANSLATE_DEFAULT_OCR_TYPE",
            "doc_translate_default_ocr_type",
        ),
    )
    doc_translate_soffice_executable: str = Field(
        default="",
        description="LibreOffice soffice 可执行文件路径；空则自动从 PATH 或常见安装目录解析。",
        validation_alias=AliasChoices(
            "DOC_TRANSLATE_SOFFICE_EXECUTABLE",
            "doc_translate_soffice_executable",
        ),
    )
    doc_translate_soffice_timeout_seconds: int = Field(
        default=120,
        ge=30,
        le=600,
        description="LibreOffice 转换 .doc 超时（秒）。",
        validation_alias=AliasChoices(
            "DOC_TRANSLATE_SOFFICE_TIMEOUT_SECONDS",
            "doc_translate_soffice_timeout_seconds",
        ),
    )


def resolve_agent_files_root() -> Path:
    """Return configured agent files root, defaulting to ``backend/data/agent-files``."""

    raw = (settings.agent_files_root or "").strip()
    if raw:
        return Path(raw).resolve()
    return (_BACKEND_DIR / "data" / "agent-files").resolve()


# Singleton loaded at import time for ``from app.config import settings``.
settings = Settings()
