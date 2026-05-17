"""Tests for ChatModelFactory."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.agent.infrastructure.chat_model_factory import ChatModelFactory
from app.exceptions import AppError


def test_raises_when_model_disabled() -> None:
    """Disabled models are rejected before constructing a client."""

    row = MagicMock()
    row.enabled = False
    row.workspace_id = uuid.uuid4()
    row.endpoint_url = "http://localhost/v1"
    row.api_key = "sk-test"
    row.model_name = "gpt-4o-mini"
    with pytest.raises(AppError) as exc:
        ChatModelFactory.from_sys_model_row(row, workspace_id=row.workspace_id)
    assert exc.value.code == "agent.model_disabled"
