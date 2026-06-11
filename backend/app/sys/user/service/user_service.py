"""Workspace member CRUD, role assignment, and account lifecycle."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.identity.models import (
    MembershipRole,
    TenantMembership,
    User,
    WorkspaceMembership,
)
from app.core.domain.identity.services import is_super_admin_user
from app.core.infrastructure.security.password import hash_password
from app.exceptions import AppError
from app.sys.dict.api.schemas import SysDictItemNodeOut
from app.sys.dict.infrastructure import repository as dict_repo
from app.sys.dict.utils.item_tree import build_item_tree
from app.sys.role.domain.db.models import SysRole
from app.sys.role.infrastructure import repository as role_repo
from app.sys.user.infrastructure import repository as repo

DEPARTMENT_DICT_CODE = "SYS_DEPARTMENT"


@dataclass
class UserListRow:
    """One workspace member row for list/detail responses."""

    user: User
    membership_role: MembershipRole
    role_ids: list[uuid.UUID]
    role_names: list[str]
    department_name: str | None
    can_hard_delete: bool


def _utc_now() -> datetime:
    """Return current UTC timestamp."""

    return datetime.now(UTC)


def _reject_self_target(
    *,
    actor_user_id: uuid.UUID,
    target_user_id: uuid.UUID,
) -> None:
    """Block delete/remove when the actor targets their own account."""

    if actor_user_id == target_user_id:
        raise AppError(
            "user.cannot_delete_self",
            "Cannot delete or remove your own account",
            403,
        )


def _is_unique_violation(exc: IntegrityError) -> bool:
    """True when the DB error is a unique constraint violation."""

    orig = getattr(exc, "orig", None)
    if orig is not None and getattr(orig, "pgcode", None) == "23505":
        return True
    return "unique" in str(exc).lower()


async def _commit_or_conflict(session: AsyncSession) -> None:
    """Commit or map unique violations to user conflict errors."""

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if _is_unique_violation(e):
            msg = str(e).lower()
            if "phone" in msg:
                raise AppError(
                    "user.phone_taken",
                    "Phone number is already registered",
                    409,
                ) from e
            raise AppError(
                "user.email_taken",
                "Email is already registered",
                409,
            ) from e
        raise


async def _resolve_department_name(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    department_item_id: uuid.UUID | None,
) -> str | None:
    """Resolve department display name from workspace SYS_DEPARTMENT dict."""

    if department_item_id is None:
        return None
    d = await dict_repo.get_dict_by_code_for_workspace(
        session, workspace_id=workspace_id, dict_code=DEPARTMENT_DICT_CODE
    )
    if d is None:
        return None
    item = await dict_repo.get_item_in_dict(
        session, dict_uuid=d.id, item_id=department_item_id
    )
    return item.name if item is not None else None


async def _validate_department_item(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    department_item_id: uuid.UUID | None,
) -> None:
    """Ensure department item belongs to workspace SYS_DEPARTMENT dict."""

    if department_item_id is None:
        return
    d = await dict_repo.get_dict_by_code_for_workspace(
        session, workspace_id=workspace_id, dict_code=DEPARTMENT_DICT_CODE
    )
    if d is None:
        raise AppError(
            "user.department_invalid",
            "Department dictionary not configured",
            400,
        )
    item = await dict_repo.get_item_in_dict(
        session, dict_uuid=d.id, item_id=department_item_id
    )
    if item is None:
        raise AppError(
            "user.department_invalid",
            "Invalid department item",
            400,
        )


async def _validate_role_ids(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    role_ids: list[uuid.UUID],
) -> None:
    """Ensure every role id exists, is active, and belongs to the workspace."""

    for role_id in role_ids:
        row = await role_repo.get_role_for_workspace(
            session, workspace_id=workspace_id, role_id=role_id
        )
        if row is None or not row.status:
            raise AppError(
                "user.role_invalid",
                "One or more role ids are invalid",
                400,
            )


async def _compute_can_hard_delete(
    session: AsyncSession,
    *,
    actor_is_super_admin: bool,
    workspace_id: uuid.UUID,
    target_user_id: uuid.UUID,
) -> bool:
    """Return whether the actor may hard-delete the target user account."""

    if actor_is_super_admin:
        return True
    count = await repo.count_all_memberships_for_user(
        session, user_id=target_user_id
    )
    if count != 1:
        return False
    member = await repo.get_member_user(
        session, workspace_id=workspace_id, user_id=target_user_id
    )
    return member is not None


async def _require_member(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[User, WorkspaceMembership]:
    """Load workspace member or raise user.not_found."""

    row = await repo.get_member_user(
        session, workspace_id=workspace_id, user_id=user_id
    )
    if row is None:
        raise AppError("user.not_found", "User not found in workspace", 404)
    return row


async def _build_list_row(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user: User,
    membership: WorkspaceMembership,
    actor_is_super_admin: bool,
) -> UserListRow:
    """Assemble one list/detail row with roles and permissions."""

    roles = await repo.list_roles_for_user_in_workspace(
        session, workspace_id=workspace_id, user_id=user.id
    )
    department_name = await _resolve_department_name(
        session,
        workspace_id=workspace_id,
        department_item_id=user.department_item_id,
    )
    can_hard_delete = await _compute_can_hard_delete(
        session,
        actor_is_super_admin=actor_is_super_admin,
        workspace_id=workspace_id,
        target_user_id=user.id,
    )
    return UserListRow(
        user=user,
        membership_role=membership.role,
        role_ids=[r.id for r in roles],
        role_names=[r.role_name for r in roles],
        department_name=department_name,
        can_hard_delete=can_hard_delete,
    )


def row_to_dict(row: UserListRow) -> dict[str, Any]:
    """Serialize a UserListRow for API responses."""

    u = row.user
    return {
        "id": u.id,
        "email": u.email,
        "nickname": u.nickname,
        "phone": u.phone,
        "status": u.status,
        "remark": u.remark,
        "department_item_id": u.department_item_id,
        "department_name": row.department_name,
        "membership_role": row.membership_role.value,
        "role_ids": row.role_ids,
        "role_names": row.role_names,
        "created_at": u.created_at,
        "update_at": u.update_at,
        "can_hard_delete": row.can_hard_delete,
    }


async def list_users_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    page: int,
    page_size: int,
    actor_is_super_admin: bool,
    email: str | None = None,
    nickname: str | None = None,
    phone: str | None = None,
    status: bool | None = None,
    membership_role: MembershipRole | None = None,
    role_id: uuid.UUID | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Return paginated workspace members and total count."""

    total = await repo.count_workspace_members(
        session,
        workspace_id=workspace_id,
        email=email,
        nickname=nickname,
        phone=phone,
        status=status,
        membership_role=membership_role,
        role_id=role_id,
    )
    offset = max(0, (page - 1) * page_size)
    rows = await repo.list_workspace_members_page(
        session,
        workspace_id=workspace_id,
        limit=page_size,
        offset=offset,
        email=email,
        nickname=nickname,
        phone=phone,
        status=status,
        membership_role=membership_role,
        role_id=role_id,
    )
    items: list[dict[str, Any]] = []
    for user, membership in rows:
        list_row = await _build_list_row(
            session,
            workspace_id=workspace_id,
            user=user,
            membership=membership,
            actor_is_super_admin=actor_is_super_admin,
        )
        items.append(row_to_dict(list_row))
    return items, total


async def get_user_detail(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    actor_is_super_admin: bool,
) -> dict[str, Any]:
    """Return one workspace member detail."""

    user, membership = await _require_member(
        session, workspace_id=workspace_id, user_id=user_id
    )
    list_row = await _build_list_row(
        session,
        workspace_id=workspace_id,
        user=user,
        membership=membership,
        actor_is_super_admin=actor_is_super_admin,
    )
    return row_to_dict(list_row)


async def create_user(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    email: str,
    password: str,
    nickname: str,
    phone: str | None,
    status: bool,
    remark: str | None,
    membership_role: MembershipRole,
    department_item_id: uuid.UUID | None,
    role_ids: list[uuid.UUID],
) -> dict[str, Any]:
    """Create a global user and add them to the workspace."""

    normalized_email = email.strip().lower()
    if len(password) < 8:
        raise AppError(
            "user.weak_password",
            "Password must be at least 8 characters",
            400,
        )
    if await repo.get_user_by_email(session, email=normalized_email) is not None:
        raise AppError(
            "user.email_taken",
            "Email is already registered",
            409,
        )
    if phone and phone.strip():
        existing_phone = await repo.get_user_by_phone(session, phone=phone)
        if existing_phone is not None:
            raise AppError(
                "user.phone_taken",
                "Phone number is already registered",
                409,
            )
    await _validate_department_item(
        session,
        workspace_id=workspace_id,
        department_item_id=department_item_id,
    )
    await _validate_role_ids(
        session, workspace_id=workspace_id, role_ids=role_ids
    )
    now = _utc_now()
    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        nickname=nickname.strip(),
        phone=phone.strip() if phone and phone.strip() else None,
        status=status,
        remark=remark.strip() if remark and remark.strip() else None,
        department_item_id=department_item_id,
        update_at=now,
    )
    tenant_id = await repo.get_tenant_id_for_workspace(
        session, workspace_id=workspace_id
    )
    if tenant_id is None:
        raise AppError("user.workspace_invalid", "Workspace not found", 404)
    await repo.add_user(session, user)
    membership = WorkspaceMembership(
        user_id=user.id,
        workspace_id=workspace_id,
        role=membership_role,
    )
    await repo.add_membership(session, membership)
    await repo.add_tenant_membership(
        session,
        TenantMembership(
            user_id=user.id,
            tenant_id=tenant_id,
            role=membership_role,
        ),
    )
    await repo.replace_user_roles_in_workspace(
        session,
        workspace_id=workspace_id,
        user_id=user.id,
        role_ids=role_ids,
    )
    await _commit_or_conflict(session)
    await session.refresh(user)
    list_row = await _build_list_row(
        session,
        workspace_id=workspace_id,
        user=user,
        membership=membership,
        actor_is_super_admin=False,
    )
    return row_to_dict(list_row)


async def update_user(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    actor_is_super_admin: bool,
    nickname: str | None = None,
    status: bool | None = None,
    password: str | None = None,
    membership_role: MembershipRole | None = None,
    department_item_id: uuid.UUID | None = None,
    update_department: bool = False,
    phone: str | None = None,
    update_phone: bool = False,
    remark: str | None = None,
    update_remark: bool = False,
    role_ids: list[uuid.UUID] | None = None,
) -> dict[str, Any]:
    """Update member profile, membership role, department, and roles."""

    user, membership = await _require_member(
        session, workspace_id=workspace_id, user_id=user_id
    )
    if nickname is not None:
        user.nickname = nickname.strip()
    if update_phone:
        normalized_phone = phone.strip() if phone and phone.strip() else None
        if normalized_phone:
            existing = await repo.get_user_by_phone(session, phone=normalized_phone)
            if existing is not None and existing.id != user.id:
                raise AppError(
                    "user.phone_taken",
                    "Phone number is already registered",
                    409,
                )
        user.phone = normalized_phone
    if status is not None:
        user.status = status
    if update_remark:
        user.remark = remark.strip() if remark and remark.strip() else None
    if password is not None and password.strip():
        if len(password) < 8:
            raise AppError(
                "user.weak_password",
                "Password must be at least 8 characters",
                400,
            )
        user.password_hash = hash_password(password)
    if membership_role is not None:
        membership.role = membership_role
    if update_department:
        if department_item_id is not None:
            await _validate_department_item(
                session,
                workspace_id=workspace_id,
                department_item_id=department_item_id,
            )
        user.department_item_id = department_item_id
    if role_ids is not None:
        await _validate_role_ids(
            session, workspace_id=workspace_id, role_ids=role_ids
        )
        await repo.replace_user_roles_in_workspace(
            session,
            workspace_id=workspace_id,
            user_id=user.id,
            role_ids=role_ids,
        )
    user.update_at = _utc_now()
    await _commit_or_conflict(session)
    await session.refresh(user)
    list_row = await _build_list_row(
        session,
        workspace_id=workspace_id,
        user=user,
        membership=membership,
        actor_is_super_admin=actor_is_super_admin,
    )
    return row_to_dict(list_row)


async def remove_membership(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> None:
    """Remove a user from the workspace without deleting the global account."""

    _reject_self_target(actor_user_id=actor_user_id, target_user_id=user_id)
    await _require_member(session, workspace_id=workspace_id, user_id=user_id)
    tenant_id = await repo.get_tenant_id_for_workspace(
        session, workspace_id=workspace_id
    )
    await repo.delete_user_roles_in_workspace(
        session, workspace_id=workspace_id, user_id=user_id
    )
    await repo.delete_membership(
        session, workspace_id=workspace_id, user_id=user_id
    )
    if tenant_id is not None:
        remaining = await repo.count_user_workspaces_in_tenant(
            session, user_id=user_id, tenant_id=tenant_id
        )
        if remaining == 0:
            await repo.delete_tenant_membership(
                session, user_id=user_id, tenant_id=tenant_id
            )
    await session.commit()


async def delete_user_account(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> None:
    """Hard-delete a user account when permitted."""

    _reject_self_target(actor_user_id=actor_user_id, target_user_id=user_id)
    await _require_member(session, workspace_id=workspace_id, user_id=user_id)
    actor_is_super = await is_super_admin_user(session, user_id=actor_user_id)
    allowed = await _compute_can_hard_delete(
        session,
        actor_is_super_admin=actor_is_super,
        workspace_id=workspace_id,
        target_user_id=user_id,
    )
    if not allowed:
        raise AppError(
            "user.delete_forbidden",
            "Not allowed to delete this user account",
            403,
        )
    await repo.delete_all_user_roles(session, user_id=user_id)
    await repo.delete_all_tenant_memberships(session, user_id=user_id)
    await repo.delete_all_memberships(session, user_id=user_id)
    await repo.delete_refresh_tokens(session, user_id=user_id)
    await repo.delete_user_row(session, user_id=user_id)
    await session.commit()


async def list_department_tree(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> list[SysDictItemNodeOut]:
    """Return SYS_DEPARTMENT dict items as a tree for the workspace."""

    d = await dict_repo.get_dict_by_code_for_workspace(
        session, workspace_id=workspace_id, dict_code=DEPARTMENT_DICT_CODE
    )
    if d is None:
        return []
    items = await dict_repo.list_items_for_dict(session, dict_uuid=d.id)
    return build_item_tree(list(items))


async def list_assignable_roles(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> list[SysRole]:
    """Return active roles in the workspace for assignment UI."""

    total = await role_repo.count_roles_for_workspace(
        session, workspace_id=workspace_id, status=True
    )
    if total == 0:
        return []
    return list(
        await role_repo.list_roles_for_workspace_page(
            session,
            workspace_id=workspace_id,
            limit=total,
            offset=0,
            status=True,
        )
    )
