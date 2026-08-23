"""GraphKB document upload validation and related service checks."""

from __future__ import annotations

import pytest

from app.exceptions import AppError


def test_reject_exe() -> None:
    """Reject upload filenames with disallowed suffixes."""

    from app.graph_kb.service.document_service import validate_upload_filename

    try:
        validate_upload_filename("x.exe")
    except AppError as exc:
        assert exc.status_code == 400
        assert exc.code == "graph_kb.file_type_unsupported"
    else:
        raise AssertionError("expected AppError")


def test_allow_md() -> None:
    """Allow markdown uploads listed in ALLOWED_UPLOAD_SUFFIXES."""

    from app.graph_kb.service.document_service import validate_upload_filename

    validate_upload_filename("note.md")


def test_reject_empty_plain_text() -> None:
    """Blank plain-text body must raise before persistence."""

    from app.graph_kb.service.document_service import validate_plain_text

    try:
        validate_plain_text("   ")
    except AppError as exc:
        assert exc.status_code == 400
        assert exc.code == "graph_kb.text_required"
    else:
        raise AssertionError("expected AppError")


@pytest.mark.asyncio
async def test_resolve_graph_models_missing_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing Chat model yields graph_kb.llm_model_not_found (400)."""

    from uuid import uuid4

    from app.graph_kb.service import model_resolver as mr

    async def _no_row(*_args, **_kwargs):
        return None

    monkeypatch.setattr(mr, "_load_enabled_model", _no_row)

    try:
        await mr.resolve_graph_models(
            session=object(),  # type: ignore[arg-type]
            workspace_id=uuid4(),
            llm_provider="openai",
            llm_name="gpt",
            emb_provider="openai",
            emb_name="emb",
        )
    except AppError as exc:
        assert exc.status_code == 400
        assert exc.code == "graph_kb.llm_model_not_found"
    else:
        raise AssertionError("expected AppError")
