import uuid

from app.sys.user.service.user_service import build_user_list_capabilities


def test_super_admin_can_pick_tenant_and_workspace():
    tid = uuid.uuid4()
    wid = uuid.uuid4()
    caps = build_user_list_capabilities(
        is_super_admin=True,
        is_tenant_admin=False,
        jwt_tenant_id=tid,
        jwt_tenant_name="Acme",
        jwt_workspace_id=wid,
        actor_workspace_role="admin",
        assignable_membership_roles=["admin", "member"],
        can_edit_membership_role=True,
    )
    assert caps["can_pick_tenant"] is True
    assert caps["can_pick_workspace"] is True
    assert caps["fixed_tenant_id"] is None
    assert caps["default_filter_tenant_id"] == tid
    assert caps["default_filter_workspace_id"] == wid


def test_tenant_admin_fixed_tenant_can_pick_workspace():
    tid = uuid.uuid4()
    wid = uuid.uuid4()
    caps = build_user_list_capabilities(
        is_super_admin=False,
        is_tenant_admin=True,
        jwt_tenant_id=tid,
        jwt_tenant_name="Acme",
        jwt_workspace_id=wid,
        actor_workspace_role=None,
        assignable_membership_roles=["admin", "member"],
        can_edit_membership_role=True,
    )
    assert caps["can_pick_tenant"] is False
    assert caps["can_pick_workspace"] is True
    assert caps["fixed_tenant_id"] == tid
    assert caps["fixed_tenant_name"] == "Acme"
    assert caps["default_filter_tenant_id"] == tid
    assert caps["default_filter_workspace_id"] == wid


def test_workspace_admin_no_scope_pickers():
    tid = uuid.uuid4()
    wid = uuid.uuid4()
    caps = build_user_list_capabilities(
        is_super_admin=False,
        is_tenant_admin=False,
        jwt_tenant_id=tid,
        jwt_tenant_name="Acme",
        jwt_workspace_id=wid,
        actor_workspace_role="admin",
        assignable_membership_roles=["admin", "member"],
        can_edit_membership_role=True,
    )
    assert caps["can_pick_tenant"] is False
    assert caps["can_pick_workspace"] is False
