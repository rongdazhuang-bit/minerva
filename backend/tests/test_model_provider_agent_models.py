"""Tests for agent conversation model listing query."""

from __future__ import annotations

import uuid

from sqlalchemy.dialects import postgresql

from app.sys.model_provider.domain.constants import MODEL_TAG_CHAT
from app.sys.model_provider.infrastructure.repository import (
    agent_conversation_models_select,
)


def test_agent_conversation_models_select_filters_chat_enabled_and_secrets() -> None:
    """Compiled SQL must filter CHAT tag, enabled, endpoint, and api_key."""

    workspace_id = uuid.uuid4()
    stmt = agent_conversation_models_select(workspace_id=workspace_id)
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "tags" in sql.lower()
    assert "enabled" in sql.lower()
    assert "endpoint_url" in sql
    assert "api_key" in sql
    assert "provider_name" in sql
    assert "model_name" in sql


def test_agent_conversation_models_select_orders_by_provider_then_model() -> None:
    """Agent model list sorts provider_name then model_name."""

    stmt = agent_conversation_models_select(workspace_id=uuid.uuid4())
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    provider_pos = sql.lower().find("provider_name")
    model_pos = sql.lower().find("model_name")
    assert provider_pos != -1 and model_pos != -1
    assert provider_pos < model_pos
