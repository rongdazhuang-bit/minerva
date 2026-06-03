"""mem0 ``Memory`` client singleton built from ``MEM0_*`` settings."""

from __future__ import annotations

from typing import Any

from app.config import settings

_memory: Any = None


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
            "config": {
                "model": settings.mem0_embedder_model,
                "api_key": settings.mem0_embedder_api_key or None,
            },
        },
    }
    llm_cfg = config["llm"]["config"]
    if settings.mem0_llm_base_url.strip():
        llm_cfg["openai_base_url"] = settings.mem0_llm_base_url.strip()
    emb_cfg = config["embedder"]["config"]
    if settings.mem0_embedder_base_url.strip():
        emb_cfg["openai_base_url"] = settings.mem0_embedder_base_url.strip()

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


def get_mem0_memory() -> Any:
    """Return process-wide mem0 ``Memory`` instance."""

    global _memory
    if _memory is None:
        from mem0 import Memory

        _memory = Memory.from_config(build_mem0_config())
    return _memory
