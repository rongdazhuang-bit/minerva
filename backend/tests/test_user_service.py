"""Unit and service-layer tests for user_service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.core.domain.identity.models import (
    MembershipRole,
    TenantMembership,
    User,
    WorkspaceMembership,
)
from app.exceptions import AppError
from app.sys.user.service import user_service as svc


def _user_row(*, user_id: uuid.UUID | None = None, email: str = "u@example.com") -> User:
    """Build a minimal User instance for tests."""

    return User(
        id=user_id or uuid.uuid4(),
        email=email,
        password_hash="hashed",
        nickname="Test User",
        status=True,
        created_at=datetime.now(UTC),
    )


def _membership_row(
    *,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    role: MembershipRole = MembershipRole.member,
) -> WorkspaceMembership:
    """Build a workspace membership row for tests."""

    return WorkspaceMembership(
        id=uuid.uuid4(),
        user_id=user_id,
        workspace_id=workspace_id,
        role=role,
    )


@pytest.mark.asyncio
async def test_create_user_adds_tenant_membership(monkeypatch) -> None:
    """Creating a user also inserts sys_tenant_user for the workspace tenant."""

    session = AsyncMock()
    ws = uuid.uuid4()
    tenant_id = uuid.uuid4()
    calls: list[str] = []
    created_user = _user_row()

    async def fake_get_by_email(_session: object, *, email: str) -> User | None:
        return None

    async def fake_get_tenant_id(
        _session: object, *, workspace_id: uuid.UUID
    ) -> uuid.UUID:
        return tenant_id

    async def fake_add_user(_session: object, row: User) -> User:
        calls.append("user")
        row.id = created_user.id
        return row

    async def fake_add_membership(
        _session: object, row: WorkspaceMembership
    ) -> WorkspaceMembership:
        calls.append("workspace_membership")
        return row

    async def fake_add_tenant_membership(
        _session: object, row: TenantMembership
    ) -> TenantMembership:
        calls.append("tenant_membership")
        assert row.user_id == created_user.id
        assert row.tenant_id == tenant_id
        assert row.role == MembershipRole.member
        return row

    async def fake_replace_roles(*_args, **_kwargs) -> None:
        calls.append("roles")

    async def fake_commit(_session: object) -> None:
        calls.append("commit")

    async def fake_build_list_row(*_args, **_kwargs):
        return svc.UserListRow(
            user=created_user,
            membership_role=MembershipRole.member,
            role_ids=[],
            role_names=[],
            department_name=None,
            can_hard_delete=False,
        )

    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.get_user_by_email",
        fake_get_by_email,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.get_tenant_id_for_workspace",
        fake_get_tenant_id,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.add_user",
        fake_add_user,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.add_membership",
        fake_add_membership,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.add_tenant_membership",
        fake_add_tenant_membership,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.replace_user_roles_in_workspace",
        fake_replace_roles,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service._commit_or_conflict",
        fake_commit,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service._build_list_row",
        fake_build_list_row,
    )
    session.refresh = AsyncMock()

    async def fake_caps(*_args, **_kwargs) -> dict[str, object]:
        return {
            "can_edit_membership_role": False,
            "assignable_membership_roles": [],
            "actor_workspace_role": None,
        }

    monkeypatch.setattr(
        "app.sys.user.service.user_service.get_actor_capabilities",
        fake_caps,
    )

    await svc.create_user(
        session,
        workspace_id=ws,
        actor_user_id=uuid.uuid4(),
        email="new@example.com",
        password="password1",
        nickname="New",
        phone=None,
        status=True,
        remark=None,
        membership_role=MembershipRole.member,
        department_item_id=None,
        role_ids=[],
    )
    assert "tenant_membership" in calls
    assert calls.index("workspace_membership") < calls.index("tenant_membership")


@pytest.mark.asyncio
async def test_remove_membership_cleans_tenant_membership_when_last_workspace(
    monkeypatch,
) -> None:
    """Removing the last workspace membership also deletes the tenant membership."""

    session = AsyncMock()
    ws = uuid.uuid4()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    calls: list[str] = []

    async def fake_require_member(
        _session: object, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ):
        return _user_row(user_id=user_id), _membership_row(
            user_id=user_id, workspace_id=workspace_id
        )

    async def fake_get_tenant_id(
        _session: object, *, workspace_id: uuid.UUID
    ) -> uuid.UUID:
        return tenant_id

    async def fake_delete_roles(*_args, **_kwargs) -> None:
        calls.append("roles")

    async def fake_delete_membership(*_args, **_kwargs) -> None:
        calls.append("workspace_membership")

    async def fake_count_workspaces(
        _session: object, *, user_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> int:
        calls.append("count")
        return 0

    async def fake_delete_tenant_membership(
        _session: object, *, user_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> None:
        calls.append("tenant_membership")

    monkeypatch.setattr(
        "app.sys.user.service.user_service._require_member",
        fake_require_member,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.get_tenant_id_for_workspace",
        fake_get_tenant_id,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.delete_user_roles_in_workspace",
        fake_delete_roles,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.delete_membership",
        fake_delete_membership,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.count_user_workspaces_in_tenant",
        fake_count_workspaces,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.delete_tenant_membership",
        fake_delete_tenant_membership,
    )

    await svc.remove_membership(
        session,
        workspace_id=ws,
        user_id=user_id,
        actor_user_id=uuid.uuid4(),
    )
    assert calls == [
        "roles",
        "workspace_membership",
        "count",
        "tenant_membership",
    ]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_user_rejects_existing_email(monkeypatch) -> None:
    """Creating with an existing email raises user.email_taken."""

    session = AsyncMock()
    existing = _user_row(email="taken@example.com")

    async def fake_get_by_email(_session: object, *, email: str) -> User:
        return existing

    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.get_user_by_email",
        fake_get_by_email,
    )

    async def fake_caps(*_args, **_kwargs) -> dict[str, object]:
        return {
            "can_edit_membership_role": False,
            "assignable_membership_roles": [],
            "actor_workspace_role": None,
        }

    monkeypatch.setattr(
        "app.sys.user.service.user_service.get_actor_capabilities",
        fake_caps,
    )

    with pytest.raises(AppError) as exc:
        await svc.create_user(
            session,
            workspace_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
            email="taken@example.com",
            password="password1",
            nickname="New",
            phone=None,
            status=True,
            remark=None,
            membership_role=MembershipRole.member,
            department_item_id=None,
            role_ids=[],
        )
    assert exc.value.code == "user.email_taken"
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_create_user_rejects_duplicate_phone(monkeypatch) -> None:
    """Non-empty phone already registered raises user.phone_taken."""

    session = AsyncMock()

    async def fake_get_by_email(_session: object, *, email: str) -> User | None:
        return None

    async def fake_get_by_phone(_session: object, *, phone: str) -> User:
        return _user_row()

    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.get_user_by_email",
        fake_get_by_email,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.get_user_by_phone",
        fake_get_by_phone,
    )

    async def fake_caps(*_args, **_kwargs) -> dict[str, object]:
        return {
            "can_edit_membership_role": False,
            "assignable_membership_roles": [],
            "actor_workspace_role": None,
        }

    monkeypatch.setattr(
        "app.sys.user.service.user_service.get_actor_capabilities",
        fake_caps,
    )

    with pytest.raises(AppError) as exc:
        await svc.create_user(
            session,
            workspace_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
            email="new@example.com",
            password="password1",
            nickname="New",
            phone="13800138000",
            status=True,
            remark=None,
            membership_role=MembershipRole.member,
            department_item_id=None,
            role_ids=[],
        )
    assert exc.value.code == "user.phone_taken"


@pytest.mark.asyncio
async def test_update_user_clears_phone_when_explicit_null(monkeypatch) -> None:
    """PATCH with phone=null clears the stored phone number."""

    session = AsyncMock()
    ws = uuid.uuid4()
    user = _user_row()
    user.phone = "13800138000"
    membership = _membership_row(user_id=user.id, workspace_id=ws)

    async def fake_require_member(
        _session: object, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ):
        return user, membership

    async def fake_build_list_row(*_args, **_kwargs):
        return svc.UserListRow(
            user=user,
            membership_role=membership.role,
            role_ids=[],
            role_names=[],
            department_name=None,
            can_hard_delete=False,
        )

    async def fake_commit(_session: object) -> None:
        return None

    monkeypatch.setattr(
        "app.sys.user.service.user_service._require_member",
        fake_require_member,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service._build_list_row",
        fake_build_list_row,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service._commit_or_conflict",
        fake_commit,
    )
    session.refresh = AsyncMock()

    await svc.update_user(
        session,
        workspace_id=ws,
        user_id=user.id,
        actor_user_id=uuid.uuid4(),
        actor_is_super_admin=False,
        phone=None,
        update_phone=True,
    )
    assert user.phone is None


@pytest.mark.asyncio
async def test_hard_delete_forbidden_multi_workspace(monkeypatch) -> None:
    """Owner/admin cannot hard-delete a user in multiple workspaces."""

    session = AsyncMock()
    ws = uuid.uuid4()
    user_id = uuid.uuid4()

    async def fake_require_member(
        _session: object, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ):
        user = _user_row(user_id=user_id)
        return user, _membership_row(user_id=user_id, workspace_id=workspace_id)

    async def fake_is_super(_session: object, *, user_id: uuid.UUID) -> bool:
        return False

    async def fake_can_hard_delete(
        _session: object,
        *,
        actor_is_super_admin: bool,
        workspace_id: uuid.UUID,
        target_user_id: uuid.UUID,
    ) -> bool:
        return False

    monkeypatch.setattr(
        "app.sys.user.service.user_service._require_member",
        fake_require_member,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.is_super_admin_user",
        fake_is_super,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service._compute_can_hard_delete",
        fake_can_hard_delete,
    )

    with pytest.raises(AppError) as exc:
        await svc.delete_user_account(
            session,
            workspace_id=ws,
            user_id=user_id,
            actor_user_id=uuid.uuid4(),
        )
    assert exc.value.code == "user.delete_forbidden"
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_user_account_cleans_tenant_memberships(monkeypatch) -> None:
    """Hard delete removes tenant memberships before the user row."""

    session = AsyncMock()
    ws = uuid.uuid4()
    user_id = uuid.uuid4()
    calls: list[str] = []

    async def fake_require_member(
        _session: object, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ):
        return _user_row(user_id=user_id), _membership_row(
            user_id=user_id, workspace_id=workspace_id
        )

    async def fake_is_super(_session: object, *, user_id: uuid.UUID) -> bool:
        return True

    async def fake_can_hard_delete(
        _session: object,
        *,
        actor_is_super_admin: bool,
        workspace_id: uuid.UUID,
        target_user_id: uuid.UUID,
    ) -> bool:
        return True

    async def fake_delete_all_user_roles(_session: object, *, user_id: uuid.UUID) -> None:
        calls.append("user_roles")

    async def fake_delete_all_tenant_memberships(
        _session: object, *, user_id: uuid.UUID
    ) -> None:
        calls.append("tenant_memberships")

    async def fake_delete_all_memberships(_session: object, *, user_id: uuid.UUID) -> None:
        calls.append("workspace_memberships")

    async def fake_delete_refresh(_session: object, *, user_id: uuid.UUID) -> None:
        calls.append("refresh_tokens")

    async def fake_delete_user_row(_session: object, *, user_id: uuid.UUID) -> None:
        calls.append("user")

    monkeypatch.setattr(
        "app.sys.user.service.user_service._require_member",
        fake_require_member,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.is_super_admin_user",
        fake_is_super,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service._compute_can_hard_delete",
        fake_can_hard_delete,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.delete_all_user_roles",
        fake_delete_all_user_roles,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.delete_all_tenant_memberships",
        fake_delete_all_tenant_memberships,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.delete_all_memberships",
        fake_delete_all_memberships,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.delete_refresh_tokens",
        fake_delete_refresh,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.repo.delete_user_row",
        fake_delete_user_row,
    )

    await svc.delete_user_account(
        session,
        workspace_id=ws,
        user_id=user_id,
        actor_user_id=uuid.uuid4(),
    )
    assert calls == [
        "user_roles",
        "tenant_memberships",
        "workspace_memberships",
        "refresh_tokens",
        "user",
    ]


@pytest.mark.asyncio
async def test_delete_user_account_rejects_self() -> None:
    """Actors cannot hard-delete their own account."""

    session = AsyncMock()
    uid = uuid.uuid4()

    with pytest.raises(AppError) as exc:
        await svc.delete_user_account(
            session,
            workspace_id=uuid.uuid4(),
            user_id=uid,
            actor_user_id=uid,
        )
    assert exc.value.code == "user.cannot_delete_self"
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_remove_membership_rejects_self() -> None:
    """Actors cannot remove themselves from the workspace."""

    session = AsyncMock()
    uid = uuid.uuid4()

    with pytest.raises(AppError) as exc:
        await svc.remove_membership(
            session,
            workspace_id=uuid.uuid4(),
            user_id=uid,
            actor_user_id=uid,
        )
    assert exc.value.code == "user.cannot_delete_self"
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    ("actor_role", "is_super", "has_membership", "expected"),
    [
        (MembershipRole.owner, False, True, ["owner", "member"]),
        (MembershipRole.admin, False, True, ["admin", "member"]),
        (MembershipRole.member, False, True, []),
        (None, True, False, ["owner", "admin", "member"]),
        (MembershipRole.admin, True, True, ["owner", "admin", "member"]),
        (MembershipRole.member, True, True, ["owner", "admin", "member"]),
    ],
)
def test_resolve_assignable_membership_roles(
    actor_role: MembershipRole | None,
    is_super: bool,
    has_membership: bool,
    expected: list[str],
) -> None:
    """Assignable membership roles follow actor matrix."""

    roles = svc.resolve_assignable_membership_roles(
        actor_workspace_role=actor_role,
        actor_is_super_admin=is_super,
        actor_has_workspace_membership=has_membership,
    )
    assert roles == expected


def test_assert_membership_role_owner_cannot_assign_admin() -> None:
    """Workspace owner cannot assign admin membership."""

    with pytest.raises(AppError) as exc:
        svc.assert_membership_role_assignable(
            membership_role=MembershipRole.admin,
            assignable_roles=["owner", "member"],
            target_current_role=None,
            actor_workspace_role=MembershipRole.owner,
        )
    assert exc.value.code == "user.membership_role_forbidden"


def test_assert_membership_role_admin_cannot_patch_owner() -> None:
    """Workspace admin cannot change an owner's membership_role."""

    with pytest.raises(AppError) as exc:
        svc.assert_membership_role_assignable(
            membership_role=MembershipRole.member,
            assignable_roles=["admin", "member"],
            target_current_role=MembershipRole.owner,
            actor_workspace_role=MembershipRole.admin,
        )
    assert exc.value.code == "user.membership_role_forbidden"


def test_assert_membership_role_super_admin_can_patch_owner() -> None:
    """Platform super admin may change an owner's membership_role."""

    svc.assert_membership_role_assignable(
        membership_role=MembershipRole.member,
        assignable_roles=["owner", "admin", "member"],
        target_current_role=MembershipRole.owner,
        actor_workspace_role=MembershipRole.admin,
        actor_is_super_admin=True,
    )


@pytest.mark.asyncio
async def test_get_actor_capabilities_super_admin(monkeypatch) -> None:
    """Super admin always receives all assignable membership roles."""

    session = AsyncMock()
    actor_id = uuid.uuid4()
    ws_id = uuid.uuid4()

    async def fake_is_super(_session: object, *, user_id: uuid.UUID) -> bool:
        return True

    async def fake_find_role(
        _session: object, *, user_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> MembershipRole | None:
        return MembershipRole.admin

    monkeypatch.setattr(
        "app.sys.user.service.user_service.is_super_admin_user",
        fake_is_super,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.find_workspace_role_for_user",
        fake_find_role,
    )

    caps = await svc.get_actor_capabilities(
        session, workspace_id=ws_id, actor_user_id=actor_id
    )
    assert caps["can_edit_membership_role"] is True
    assert caps["assignable_membership_roles"] == ["owner", "admin", "member"]
    assert caps["can_pick_tenant_workspace"] is True


@pytest.mark.asyncio
async def test_get_actor_capabilities_admin(monkeypatch) -> None:
    """Admin actor receives admin/member assignable roles."""

    session = AsyncMock()
    actor_id = uuid.uuid4()
    ws_id = uuid.uuid4()

    async def fake_is_super(_session: object, *, user_id: uuid.UUID) -> bool:
        return False

    async def fake_find_role(
        _session: object, *, user_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> MembershipRole | None:
        return MembershipRole.admin

    monkeypatch.setattr(
        "app.sys.user.service.user_service.is_super_admin_user",
        fake_is_super,
    )
    monkeypatch.setattr(
        "app.sys.user.service.user_service.find_workspace_role_for_user",
        fake_find_role,
    )

    caps = await svc.get_actor_capabilities(
        session, workspace_id=ws_id, actor_user_id=actor_id
    )
    assert caps["can_edit_membership_role"] is True
    assert caps["assignable_membership_roles"] == ["admin", "member"]
    assert caps["can_pick_tenant_workspace"] is False
