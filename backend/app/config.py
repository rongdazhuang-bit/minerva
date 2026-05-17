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
    agent_node_stream_segment_max_chars: int = Field(
        default=2048,
        ge=256,
        description="Agent 运行节点 `llm.stream_segment` 单段累计文本上限（字符），与 chunk 阈值先达先生效。",
        validation_alias=AliasChoices(
            "AGENT_NODE_STREAM_SEGMENT_MAX_CHARS",
            "agent_node_stream_segment_max_chars",
        ),
    )
    agent_node_stream_segment_max_chunks: int = Field(
        default=50,
        ge=1,
        description="Agent 运行节点流式分段：上游 chunk 计数阈值，与字符阈值先达先生效。",
        validation_alias=AliasChoices(
            "AGENT_NODE_STREAM_SEGMENT_MAX_CHUNKS",
            "agent_node_stream_segment_max_chunks",
        ),
    )
    agent_node_stream_segment_max_rows: int = Field(
        default=500,
        ge=10,
        description="单次 agent run 中 `llm.stream_segment` 节点最大行数，超出后合并并标记 overflow。",
        validation_alias=AliasChoices(
            "AGENT_NODE_STREAM_SEGMENT_MAX_ROWS",
            "agent_node_stream_segment_max_rows",
        ),
    )
    agent_json_snapshot_max_bytes: int = Field(
        default=65536,
        ge=4096,
        description="Agent 节点 `inputs_json`/`outputs_json` 等 JSON 快照写入前的最大字节数（截断）。",
        validation_alias=AliasChoices(
            "AGENT_JSON_SNAPSHOT_MAX_BYTES",
            "agent_json_snapshot_max_bytes",
        ),
    )
    agent_max_tool_rounds: int = Field(
        default=16,
        ge=1,
        description="单次 run 内 LLM↔tool 循环最大轮数，防止无限工具调用。",
        validation_alias=AliasChoices(
            "AGENT_MAX_TOOL_ROUNDS",
            "agent_max_tool_rounds",
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
    agent_tool_timeout_seconds: float = Field(
        default=60.0,
        ge=1.0,
        description="单个 tool 执行超时（秒）。",
        validation_alias=AliasChoices(
            "AGENT_TOOL_TIMEOUT_SECONDS",
            "agent_tool_timeout_seconds",
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


def resolve_agent_files_root() -> Path:
    """Return configured agent files root, defaulting to ``backend/data/agent-files``."""

    raw = (settings.agent_files_root or "").strip()
    if raw:
        return Path(raw).resolve()
    return (_BACKEND_DIR / "data" / "agent-files").resolve()


# Singleton loaded at import time for ``from app.config import settings``.
settings = Settings()
