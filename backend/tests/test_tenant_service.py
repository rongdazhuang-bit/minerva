"""Unit tests for tenant_service slug validation."""

import pytest

from app.exceptions import AppError
from app.sys.tenant.service import tenant_service as svc


def test_validate_slug_accepts_valid_slug() -> None:
    """Lowercase alphanumeric slug with hyphen is valid."""

    assert svc.validate_slug("acme-corp") == "acme-corp"


def test_validate_slug_rejects_invalid_chars() -> None:
    """Slug with spaces is invalid even after lowercasing."""

    with pytest.raises(AppError) as exc:
        svc.validate_slug("My Tenant")
    assert exc.value.code == "tenant.invalid_slug"


def test_validate_slug_trims_and_lowercases() -> None:
    """Slug is normalized before validation."""

    assert svc.validate_slug("  Acme-1  ") == "acme-1"
