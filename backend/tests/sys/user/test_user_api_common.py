"""Tests for user API shared helpers."""

from app.core.domain.identity.models import MembershipRole
from app.sys.user.api.common import parse_membership_role


def test_parse_membership_role_admin():
    assert parse_membership_role("admin") == MembershipRole.admin


def test_parse_membership_role_empty():
    assert parse_membership_role(None) is None
    assert parse_membership_role("") is None
    assert parse_membership_role("  ") is None
