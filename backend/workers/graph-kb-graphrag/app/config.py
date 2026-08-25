"""GraphRAG worker settings from ``.env.<WORKER_ENV>`` in the worker package root."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Self

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_WORKER_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_ROOT = _WORKER_ROOT.parent.parent


def _discover_worker_env() -> str:
    """``WORKER_ENV`` from the process environment; default ``local``."""

    v = os.environ.get("WORKER_ENV", "").strip()
    return v or "local"


def _env_file_paths() -> tuple[str, ...] | None:
    """Load only ``backend/workers/graph-kb-graphrag/.env.<WORKER_ENV>`` when present."""

    path = _WORKER_ROOT / f".env.{_discover_worker_env()}"
    return (str(path),) if path.is_file() else None


class Settings(BaseSettings):
    """Typed configuration for the GraphRAG GraphKB worker process."""

    model_config = SettingsConfigDict(
        env_file=_env_file_paths(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    worker_env: str = Field(
        default_factory=_discover_worker_env,
        validation_alias=AliasChoices("WORKER_ENV", "worker_env"),
    )
    graph_kb_graphrag_worker_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "GRAPH_KB_GRAPHRAG_WORKER_API_KEY",
            "graph_kb_graphrag_worker_api_key",
        ),
    )
    graph_kb_worker_fake: bool = Field(
        default=False,
        validation_alias=AliasChoices("GRAPH_KB_WORKER_FAKE", "graph_kb_worker_fake"),
    )
    graph_kb_data: str = Field(
        default="",
        description="GraphRAG silo parent; empty uses backend/data/graph_kb.",
        validation_alias=AliasChoices("GRAPH_KB_DATA", "graph_kb_data"),
    )
    graph_kb_llm_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("GRAPH_KB_LLM_BASE_URL", "graph_kb_llm_base_url"),
    )
    graph_kb_llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GRAPH_KB_LLM_API_KEY", "graph_kb_llm_api_key"),
    )
    graph_kb_llm_model: str = Field(
        default="",
        validation_alias=AliasChoices("GRAPH_KB_LLM_MODEL", "graph_kb_llm_model"),
    )
    graph_kb_embedding_base_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "GRAPH_KB_EMBEDDING_BASE_URL",
            "graph_kb_embedding_base_url",
        ),
    )
    graph_kb_embedding_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "GRAPH_KB_EMBEDDING_API_KEY",
            "graph_kb_embedding_api_key",
        ),
    )
    graph_kb_embedding_model: str = Field(
        default="",
        validation_alias=AliasChoices(
            "GRAPH_KB_EMBEDDING_MODEL",
            "graph_kb_embedding_model",
        ),
    )

    def llm_credentials(self) -> dict[str, str]:
        """OpenAI-compatible Chat credentials from worker settings."""

        return {
            "base_url": self.graph_kb_llm_base_url.strip(),
            "api_key": self.graph_kb_llm_api_key.strip(),
            "model": self.graph_kb_llm_model.strip() or "gpt-4o-mini",
        }

    def embedding_credentials(self) -> dict[str, str]:
        """OpenAI-compatible Embedding credentials from worker settings."""

        return {
            "base_url": self.graph_kb_embedding_base_url.strip(),
            "api_key": self.graph_kb_embedding_api_key.strip(),
            "model": self.graph_kb_embedding_model.strip() or "text-embedding-3-small",
        }

    @field_validator("graph_kb_worker_fake", mode="before")
    @classmethod
    def parse_worker_fake_flag(cls, value: Any) -> bool:
        """Accept ``1`` / ``true`` / ``yes`` for fake-engine mode."""

        if isinstance(value, bool):
            return value
        if value is None:
            return False
        text = str(value).strip().lower()
        return text in {"1", "true", "yes", "on"}

    @model_validator(mode="after")
    def require_api_key_and_models(self) -> Self:
        """Worker API key is mandatory; LLM/embedding required when not in fake mode."""

        if not self.graph_kb_graphrag_worker_api_key.strip():
            raise ValueError(
                "GRAPH_KB_GRAPHRAG_WORKER_API_KEY is required "
                f"(profile .env.{self.worker_env})"
            )
        if self.graph_kb_worker_fake:
            return self
        required = {
            "GRAPH_KB_LLM_BASE_URL": self.graph_kb_llm_base_url,
            "GRAPH_KB_LLM_API_KEY": self.graph_kb_llm_api_key,
            "GRAPH_KB_LLM_MODEL": self.graph_kb_llm_model,
            "GRAPH_KB_EMBEDDING_BASE_URL": self.graph_kb_embedding_base_url,
            "GRAPH_KB_EMBEDDING_API_KEY": self.graph_kb_embedding_api_key,
            "GRAPH_KB_EMBEDDING_MODEL": self.graph_kb_embedding_model,
        }
        missing = [name for name, value in required.items() if not (value or "").strip()]
        if missing:
            raise ValueError(
                "When GRAPH_KB_WORKER_FAKE is not enabled, required: "
                + ", ".join(missing)
            )
        return self

    def resolve_graph_kb_data(self) -> Path:
        """Return GraphRAG data root; default ``backend/data/graph_kb`` when unset."""

        raw = (self.graph_kb_data or "").strip()
        if raw:
            return Path(raw).resolve()
        return (_BACKEND_ROOT / "data" / "graph_kb").resolve()


def load_settings() -> Settings:
    """Load settings or exit the process with a readable error."""

    try:
        return Settings()
    except Exception as exc:  # noqa: BLE001 — startup guard
        print(f"[error] GraphRAG worker config: {exc}", file=sys.stderr)
        sys.exit(1)


settings = load_settings()
