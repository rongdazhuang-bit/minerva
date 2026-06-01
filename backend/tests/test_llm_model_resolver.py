"""Tests for sys_models resolution in app.llm."""

from __future__ import annotations

import uuid

import pytest

from app.exceptions import AppError
from app.llm.domain.resolved_model import CHAT_MODEL_TAGS, ResolvedModel
from app.llm.service.model_resolver import resolve_model
from app.sys.model_provider.domain.db.models import SysModel


class _FakeResult:
    """Minimal SQLAlchemy result stub."""

    def __init__(self, row: SysModel | None) -> None:
        """Store the row returned by scalar_one_or_none."""

        self._row = row

    def scalar_one_or_none(self) -> SysModel | None:
        """Return the configured row."""

        return self._row


class _FakeSession:
    """Minimal async session stub."""

    def __init__(self, row: SysModel | None) -> None:
        """Store model row for execute()."""

        self._row = row

    async def execute(self, _stmt):  # noqa: ANN001
        """Return fake query result."""

        return _FakeResult(self._row)


def _row(**overrides) -> SysModel:  # noqa: ANN003
    """Build a SysModel test instance."""

    ws = uuid.uuid4()
    mid = uuid.uuid4()
    data = dict(
        id=mid,
        workspace_id=ws,
        provider_name="openai",
        model_name="gpt-4o-mini",
        enabled=True,
        auth_type="api_key",
        endpoint_url="https://example.com/v1/chat/completions",
        api_key="secret",
        auth_name=None,
        auth_passwd=None,
        context_size=None,
        max_tokens=None,
        model_config=None,
        tags=["TEXT"],
        create_at=None,
        update_at=None,
    )
    data.update(overrides)
    return SysModel(**data)


@pytest.mark.asyncio
async def test_resolve_model_success() -> None:
    """Enabled model with matching tags resolves to ResolvedModel."""

    row = _row()
    session = _FakeSession(row)
    resolved = await resolve_model(
        session,
        workspace_id=row.workspace_id,
        model_id=row.id,
        allowed_tags=CHAT_MODEL_TAGS,
    )
    assert isinstance(resolved, ResolvedModel)
    assert resolved.model_name == "gpt-4o-mini"
    assert resolved.endpoint_url.endswith("/chat/completions")


@pytest.mark.asyncio
async def test_resolve_model_tag_mismatch() -> None:
    """Wrong tags for endpoint raises ai.model_tag_mismatch."""

    row = _row(tags=["EMBEDDINGS"])
    session = _FakeSession(row)
    with pytest.raises(AppError) as exc:
        await resolve_model(
            session,
            workspace_id=row.workspace_id,
            model_id=row.id,
            allowed_tags=CHAT_MODEL_TAGS,
        )
    assert exc.value.code == "ai.model_tag_mismatch"
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_resolve_model_excluded_tag() -> None:
    """Excluded tag intersection rejects otherwise allowed models."""

    row = _row(tags=["TEXT", "TRANSLATE"])
    session = _FakeSession(row)
    with pytest.raises(AppError) as exc:
        await resolve_model(
            session,
            workspace_id=row.workspace_id,
            model_id=row.id,
            allowed_tags=frozenset({"TEXT"}),
            excluded_tags=frozenset({"TRANSLATE"}),
        )
    assert exc.value.code == "ai.model_tag_mismatch"


@pytest.mark.asyncio
async def test_resolve_model_misconfigured() -> None:
    """Missing endpoint_url or api_key raises ai.model_misconfigured."""

    row = _row(endpoint_url="", api_key="")
    session = _FakeSession(row)
    with pytest.raises(AppError) as exc:
        await resolve_model(
            session,
            workspace_id=row.workspace_id,
            model_id=row.id,
            allowed_tags=CHAT_MODEL_TAGS,
        )
    assert exc.value.code == "ai.model_misconfigured"


@pytest.mark.asyncio
async def test_resolve_model_none_auth_uses_dash_key() -> None:
    """NONE auth models without api_key use placeholder dash."""

    row = _row(auth_type="NONE", api_key="")
    session = _FakeSession(row)
    resolved = await resolve_model(
        session,
        workspace_id=row.workspace_id,
        model_id=row.id,
        allowed_tags=CHAT_MODEL_TAGS,
    )
    assert resolved.api_key == "-"
