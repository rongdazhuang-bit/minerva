"""Application settings: env vars, single dotenv file per profile, typed defaults."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Self

from pydantic import AliasChoices, Field, model_validator
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
    log_level: str = Field(
        default="INFO",
        description="Application log level: DEBUG, INFO, WARNING, ERROR, or CRITICAL.",
        validation_alias=AliasChoices("LOG_LEVEL", "log_level"),
    )
    log_dir: str = Field(
        default="logs",
        description="Log directory relative to backend/ unless an absolute path is provided.",
        validation_alias=AliasChoices("LOG_DIR", "log_dir"),
    )
    log_retention_days: int = Field(
        default=7,
        ge=1,
        le=365,
        description="Number of daily log files to keep.",
        validation_alias=AliasChoices("LOG_RETENTION_DAYS", "log_retention_days"),
    )
    log_body_enabled: bool = Field(
        default=True,
        description="When True, HTTP middleware logs sanitized request bodies (not responses).",
        validation_alias=AliasChoices("LOG_BODY_ENABLED", "log_body_enabled"),
    )
    log_body_max_chars: int = Field(
        default=20000,
        ge=0,
        le=1_000_000,
        description="Maximum characters kept for one logged HTTP request body.",
        validation_alias=AliasChoices("LOG_BODY_MAX_CHARS", "log_body_max_chars"),
    )
    log_file_enabled: bool = Field(
        default=True,
        description="When True, application logs are written to rotating local log files.",
        validation_alias=AliasChoices("LOG_FILE_ENABLED", "log_file_enabled"),
    )
    log_stdout_enabled: bool = Field(
        default=True,
        description="When True, application logs are written to stdout.",
        validation_alias=AliasChoices("LOG_STDOUT_ENABLED", "log_stdout_enabled"),
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
    celery_scheduled_task_lock_ttl_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description=(
            "Redis TTL for scheduled-task singleton locks; auto-releases if a worker dies mid-run."
        ),
        validation_alias=AliasChoices(
            "CELERY_SCHEDULED_TASK_LOCK_TTL_SECONDS",
            "celery_scheduled_task_lock_ttl_seconds",
        ),
    )
    celery_redis_socket_connect_timeout: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Redis socket connect timeout (seconds) for Celery broker and auxiliary clients.",
        validation_alias=AliasChoices(
            "CELERY_REDIS_SOCKET_CONNECT_TIMEOUT",
            "celery_redis_socket_connect_timeout",
        ),
    )
    celery_redis_socket_timeout: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Redis socket read/write timeout (seconds) for Celery broker and auxiliary clients.",
        validation_alias=AliasChoices(
            "CELERY_REDIS_SOCKET_TIMEOUT",
            "celery_redis_socket_timeout",
        ),
    )
    celery_redis_health_check_interval: int = Field(
        default=30,
        ge=0,
        le=600,
        description="Redis connection pool health check interval (seconds); 0 disables.",
        validation_alias=AliasChoices(
            "CELERY_REDIS_HEALTH_CHECK_INTERVAL",
            "celery_redis_health_check_interval",
        ),
    )
    celery_broker_connection_max_retries: int = Field(
        default=0,
        ge=0,
        le=1000,
        description=(
            "Celery broker connect retries on worker/beat startup; 0 means unlimited retries."
        ),
        validation_alias=AliasChoices(
            "CELERY_BROKER_CONNECTION_MAX_RETRIES",
            "celery_broker_connection_max_retries",
        ),
    )
    celery_worker_pool: str | None = Field(
        default=None,
        description=(
            "Celery worker pool override (threads|solo|prefork). "
            "Empty uses platform default in celery_app (Windows: threads)."
        ),
        validation_alias=AliasChoices(
            "MINERVA_CELERY_POOL",
            "CELERY_WORKER_POOL",
            "celery_worker_pool",
        ),
    )
    celery_worker_concurrency: int = Field(
        default=4,
        ge=1,
        le=64,
        description="Worker concurrency when pool is threads or prefork.",
        validation_alias=AliasChoices(
            "MINERVA_CELERY_CONCURRENCY",
            "CELERY_WORKER_CONCURRENCY",
            "celery_worker_concurrency",
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
    agent_memory_backend: Literal["sql", "mem0"] = Field(
        default="sql",
        description="Agent 长期记忆后端：sql（二维表）或 mem0（pgvector + Neo4j）。",
        validation_alias=AliasChoices("AGENT_MEMORY_BACKEND", "agent_memory_backend"),
    )
    mem0_database_url: str = Field(
        default="",
        description="mem0 pgvector 库连接串（库名通常为 minerva_memory）。",
        validation_alias=AliasChoices("MEM0_DATABASE_URL", "mem0_database_url"),
    )
    mem0_pg_host: str = Field(
        default="",
        validation_alias=AliasChoices("MEM0_PG_HOST", "mem0_pg_host"),
    )
    mem0_pg_port: int = Field(
        default=5432,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("MEM0_PG_PORT", "mem0_pg_port"),
    )
    mem0_pg_user: str = Field(
        default="",
        validation_alias=AliasChoices("MEM0_PG_USER", "mem0_pg_user"),
    )
    mem0_pg_password: str = Field(
        default="",
        validation_alias=AliasChoices("MEM0_PG_PASSWORD", "mem0_pg_password"),
    )
    mem0_pg_dbname: str = Field(
        default="minerva_memory",
        validation_alias=AliasChoices("MEM0_PG_DBNAME", "mem0_pg_dbname"),
    )
    mem0_vector_collection: str = Field(
        default="mem0",
        validation_alias=AliasChoices("MEM0_VECTOR_COLLECTION", "mem0_vector_collection"),
    )
    mem0_embedding_dims: int = Field(
        default=1536,
        ge=1,
        validation_alias=AliasChoices("MEM0_EMBEDDING_DIMS", "mem0_embedding_dims"),
    )
    mem0_pg_pool_min: int = Field(
        default=1,
        ge=1,
        validation_alias=AliasChoices("MEM0_PG_POOL_MIN", "mem0_pg_pool_min"),
    )
    mem0_pg_pool_max: int = Field(
        default=5,
        ge=1,
        validation_alias=AliasChoices("MEM0_PG_POOL_MAX", "mem0_pg_pool_max"),
    )
    mem0_graph_enabled: bool = Field(
        default=True,
        description="为 False 时 mem0 仅使用 pgvector，不连接 Neo4j。",
        validation_alias=AliasChoices("MEM0_GRAPH_ENABLED", "mem0_graph_enabled"),
    )
    mem0_neo4j_url: str = Field(
        default="",
        validation_alias=AliasChoices("MEM0_NEO4J_URL", "mem0_neo4j_url"),
    )
    mem0_neo4j_username: str = Field(
        default="neo4j",
        validation_alias=AliasChoices("MEM0_NEO4J_USERNAME", "mem0_neo4j_username"),
    )
    mem0_neo4j_password: str = Field(
        default="",
        validation_alias=AliasChoices("MEM0_NEO4J_PASSWORD", "mem0_neo4j_password"),
    )
    mem0_neo4j_database: str = Field(
        default="neo4j",
        validation_alias=AliasChoices("MEM0_NEO4J_DATABASE", "mem0_neo4j_database"),
    )
    mem0_neo4j_base_label: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("MEM0_NEO4J_BASE_LABEL", "mem0_neo4j_base_label"),
    )
    mem0_llm_provider: str = Field(
        default="openai",
        validation_alias=AliasChoices("MEM0_LLM_PROVIDER", "mem0_llm_provider"),
    )
    mem0_llm_model: str = Field(
        default="",
        validation_alias=AliasChoices("MEM0_LLM_MODEL", "mem0_llm_model"),
    )
    mem0_llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("MEM0_LLM_API_KEY", "mem0_llm_api_key"),
    )
    mem0_llm_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("MEM0_LLM_BASE_URL", "mem0_llm_base_url"),
    )
    mem0_embedder_provider: str = Field(
        default="openai",
        validation_alias=AliasChoices("MEM0_EMBEDDER_PROVIDER", "mem0_embedder_provider"),
    )
    mem0_embedder_model: str = Field(
        default="",
        validation_alias=AliasChoices("MEM0_EMBEDDER_MODEL", "mem0_embedder_model"),
    )
    mem0_embedder_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("MEM0_EMBEDDER_API_KEY", "mem0_embedder_api_key"),
    )
    mem0_embedder_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("MEM0_EMBEDDER_BASE_URL", "mem0_embedder_base_url"),
    )
    mem0_embedder_direct_base_url: str = Field(
        default="",
        description=(
            "Embedding 专用 OpenAI 兼容根地址（如 vLLM/TEI /v1）。"
            "设置后优先于 MEM0_EMBEDDER_BASE_URL，用于绕过仅支持 chat 的 LiteLLM 代理。"
        ),
        validation_alias=AliasChoices(
            "MEM0_EMBEDDER_DIRECT_BASE_URL",
            "mem0_embedder_direct_base_url",
        ),
    )
    agent_memory_mem0_rerank_enabled: bool = Field(
        default=False,
        description="mem0 search 是否启用 rerank（需 mem0 reranker 配置）。",
        validation_alias=AliasChoices(
            "AGENT_MEMORY_MEM0_RERANK_ENABLED",
            "agent_memory_mem0_rerank_enabled",
        ),
    )
    agent_memory_llm_compress_enabled: bool = Field(
        default=False,
        description="Run 内是否对召回记忆做 LLM 压缩（mem0 路径）。",
        validation_alias=AliasChoices(
            "AGENT_MEMORY_LLM_COMPRESS_ENABLED",
            "agent_memory_llm_compress_enabled",
        ),
    )
    agent_memory_profile_llm_enabled: bool = Field(
        default=False,
        description="Run 时现场 session 画像是否经 LLM 合成。",
        validation_alias=AliasChoices(
            "AGENT_MEMORY_PROFILE_LLM_ENABLED",
            "agent_memory_profile_llm_enabled",
        ),
    )
    agent_memory_compress_celery_enabled: bool = Field(
        default=False,
        description="为 True 时注册 mem0 记忆 Celery 压缩任务。",
        validation_alias=AliasChoices(
            "AGENT_MEMORY_COMPRESS_CELERY_ENABLED",
            "agent_memory_compress_celery_enabled",
        ),
    )
    agent_memory_compress_cron: str | None = Field(
        default=None,
        description="mem0 压缩 beat cron（sys_celery 行可另行配置）。",
        validation_alias=AliasChoices(
            "AGENT_MEMORY_COMPRESS_CRON",
            "agent_memory_compress_cron",
        ),
    )
    agent_memory_compress_max_age_days: int = Field(
        default=90,
        ge=1,
        description="Celery 压缩任务处理的记忆最大保留天数阈值。",
        validation_alias=AliasChoices(
            "AGENT_MEMORY_COMPRESS_MAX_AGE_DAYS",
            "agent_memory_compress_max_age_days",
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
    agent_enable_thinking: bool = Field(
        default=False,
        description="Agent 默认是否向上游请求思考模式（Run 与 model_config 可覆盖）。",
        validation_alias=AliasChoices("AGENT_ENABLE_THINKING", "agent_enable_thinking"),
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
    layout_page_raster_prefix: str = Field(
        default="ocr/page-raster",
        description="S3 module prefix for per-page OCR layout preview rasters.",
        validation_alias=AliasChoices(
            "LAYOUT_PAGE_RASTER_PREFIX",
            "layout_page_raster_prefix",
        ),
    )
    layout_schema_version: int = Field(
        default=1,
        ge=1,
        le=32767,
        description="Layout Document Model JSON schema version stored in OCR page rows.",
        validation_alias=AliasChoices(
            "LAYOUT_SCHEMA_VERSION",
            "layout_schema_version",
        ),
    )
    dataset_vector_store: str = Field(
        default="pgvector",
        description="知识库向量后端：pgvector / qdrant / weaviate 等。",
        validation_alias=AliasChoices("DATASET_VECTOR_STORE", "dataset_vector_store"),
    )
    dataset_vector_index_name_prefix: str = Field(
        default="Vector_index",
        description="向量 collection 名称前缀。",
        validation_alias=AliasChoices(
            "DATASET_VECTOR_INDEX_NAME_PREFIX",
            "dataset_vector_index_name_prefix",
        ),
    )
    dataset_keyword_store: str = Field(
        default="jieba",
        description="经济模式关键词提取后端。",
        validation_alias=AliasChoices("DATASET_KEYWORD_STORE", "dataset_keyword_store"),
    )
    dataset_batch_upload_limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="知识库单批上传文件数上限。",
        validation_alias=AliasChoices(
            "DATASET_BATCH_UPLOAD_LIMIT",
            "dataset_batch_upload_limit",
        ),
    )
    dataset_max_files_per_dataset: int = Field(
        default=5,
        ge=1,
        le=50,
        description="创建知识库时文件总数上限。",
        validation_alias=AliasChoices(
            "DATASET_MAX_FILES_PER_DATASET",
            "dataset_max_files_per_dataset",
        ),
    )
    dataset_single_file_size_limit_mb: int = Field(
        default=100,
        ge=1,
        le=500,
        description="知识库单文件大小上限（MB）。",
        validation_alias=AliasChoices(
            "DATASET_SINGLE_FILE_SIZE_LIMIT_MB",
            "dataset_single_file_size_limit_mb",
        ),
    )
    dataset_pgvector_url: str = Field(
        default="",
        description="pgvector 连接串；空则使用 sync_database_url 对应库。",
        validation_alias=AliasChoices("DATASET_PGVECTOR_URL", "dataset_pgvector_url"),
    )
    dataset_qdrant_url: str = Field(
        default="",
        validation_alias=AliasChoices("DATASET_QDRANT_URL", "dataset_qdrant_url"),
    )
    dataset_qdrant_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DATASET_QDRANT_API_KEY", "dataset_qdrant_api_key"),
    )
    dataset_weaviate_endpoint: str = Field(
        default="",
        validation_alias=AliasChoices("DATASET_WEAVIATE_ENDPOINT", "dataset_weaviate_endpoint"),
    )
    dataset_weaviate_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DATASET_WEAVIATE_API_KEY", "dataset_weaviate_api_key"),
    )

    @model_validator(mode="after")
    def validate_agent_memory_backend_config(self) -> Self:
        """When mem0 backend is selected, require PG and optional Neo4j settings."""

        if self.agent_memory_backend != "mem0":
            return self
        import importlib.util

        if importlib.util.find_spec("mem0") is None:
            raise ValueError(
                "AGENT_MEMORY_BACKEND=mem0 requires the mem0ai package "
                '(PyPI name "mem0ai", import "mem0"). '
                'Install with: cd backend && pip install -e ".[dev]" '
                "(includes mem0ai[nlp] for spaCy)."
            )
        if importlib.util.find_spec("spacy") is None:
            raise ValueError(
                "AGENT_MEMORY_BACKEND=mem0 requires spaCy (mem0ai[nlp]). "
                'Install with: cd backend && pip install -e ".[dev]"'
            )
        has_db_url = bool(self.mem0_database_url.strip())
        has_pg_parts = bool(self.mem0_pg_host.strip()) and bool(self.mem0_pg_user.strip())
        if not has_db_url and not has_pg_parts:
            raise ValueError(
                "AGENT_MEMORY_BACKEND=mem0 requires MEM0_DATABASE_URL or "
                "MEM0_PG_HOST with MEM0_PG_USER"
            )
        if self.mem0_graph_enabled:
            if not self.mem0_neo4j_url.strip():
                raise ValueError(
                    "MEM0_GRAPH_ENABLED=true requires MEM0_NEO4J_URL"
                )
            if not self.mem0_neo4j_password.strip():
                raise ValueError(
                    "MEM0_GRAPH_ENABLED=true requires MEM0_NEO4J_PASSWORD"
                )
        return self


def resolve_agent_files_root() -> Path:
    """Return configured agent files root, defaulting to ``backend/data/agent-files``."""

    raw = (settings.agent_files_root or "").strip()
    if raw:
        return Path(raw).resolve()
    return (_BACKEND_DIR / "data" / "agent-files").resolve()


# Singleton loaded at import time for ``from app.config import settings``.
settings = Settings()
