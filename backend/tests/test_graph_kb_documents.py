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
