"""mem0 ``Memory`` client singleton built from ``MEM0_*`` settings."""

from __future__ import annotations

import uuid
from typing import Any

from app.agent.memory.mem0.embedder_config import build_embedder_config
from app.agent.memory.mem0.logging_embedder import wrap_embedder_with_logging
from app.agent.memory.mem0.logging_neo4j import wrap_mem0_memory_graph_with_logging
from app.agent.memory.mem0.spacy_runtime import ensure_mem0_spacy_ready
from app.config import settings

_memory: Any = None

_MEM0_INSTALL_HINT = (
    "Install the mem0 SDK with: cd backend && pip install -e \".[dev]\" "
    '(includes "mem0ai[nlp]" on PyPI; import name is "mem0").'
)


def ensure_mem0_installed() -> None:
    """Raise a clear error when ``mem0ai`` is missing but mem0 backend is enabled."""

    try:
        import mem0  # noqa: F401
    except ModuleNotFoundError as e:
        raise RuntimeError(
            f"AGENT_MEMORY_BACKEND=mem0 requires the mem0ai package. {_MEM0_INSTALL_HINT}"
        ) from e


def build_mem0_config() -> dict[str, Any]:
    """Build ``Memory.from_config`` dict from application settings."""

    pg: dict[str, Any] = {
        "collection_name": settings.mem0_vector_collection,
        "embedding_model_dims": settings.mem0_embedding_dims,
        "minconn": settings.mem0_pg_pool_min,
        "maxconn": settings.mem0_pg_pool_max,
    }
    db_url = (settings.mem0_database_url or "").strip()
    if db_url:
        pg["connection_string"] = db_url
    else:
        pg["dbname"] = settings.mem0_pg_dbname
        pg["host"] = settings.mem0_pg_host
        pg["port"] = str(settings.mem0_pg_port)
        pg["user"] = settings.mem0_pg_user
        pg["password"] = settings.mem0_pg_password

    config: dict[str, Any] = {
        "vector_store": {"provider": "pgvector", "config": pg},
        "llm": {
            "provider": settings.mem0_llm_provider,
            "config": {
                "model": settings.mem0_llm_model,
                "api_key": settings.mem0_llm_api_key or None,
            },
        },
        "embedder": {
            "provider": settings.mem0_embedder_provider,
            "config": build_embedder_config(),
        },
    }
    llm_cfg = config["llm"]["config"]
    if settings.mem0_llm_base_url.strip():
        llm_cfg["openai_base_url"] = settings.mem0_llm_base_url.strip()

    if settings.mem0_graph_enabled:
        neo: dict[str, Any] = {
            "url": settings.mem0_neo4j_url,
            "username": settings.mem0_neo4j_username,
            "password": settings.mem0_neo4j_password,
            "database": settings.mem0_neo4j_database,
        }
        if settings.mem0_neo4j_base_label is not None:
            neo["base_label"] = settings.mem0_neo4j_base_label
        config["graph_store"] = {"provider": "neo4j", "config": neo}

    return config


def mem0_entity_filters(
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID | None = None,
) -> dict[str, str]:
    """Build mem0ai 2.x ``filters`` dict (``user_id`` = workspace, ``run_id`` = session)."""

    filters: dict[str, str] = {"user_id": str(workspace_id)}
    if session_id is not None:
        filters["run_id"] = str(session_id)
    return filters


def get_mem0_memory() -> Any:
    """Return process-wide mem0 ``Memory`` instance."""

    global _memory
    if _memory is None:
        ensure_mem0_installed()
        from mem0 import Memory

        _memory = Memory.from_config(build_mem0_config())
        if getattr(_memory, "embedding_model", None) is not None:
            _memory.embedding_model = wrap_embedder_with_logging(_memory.embedding_model)
        if settings.mem0_graph_enabled:
            wrap_mem0_memory_graph_with_logging(_memory)
        ensure_mem0_spacy_ready()
    return _memory


def reset_mem0_memory_cache() -> None:
    """Clear cached mem0 client and embedder resolution (for tests)."""

    global _memory
    from app.agent.memory.mem0 import embedder_config

    _memory = None
    embedder_config._resolved_embedder = None
