-- Scoped authorization grants: roles, direct permissions, tenant admins
CREATE TABLE IF NOT EXISTS public.sys_user_grant (
  id                  UUID         NOT NULL,
  user_id             UUID         NOT NULL,
  grant_type          VARCHAR(32)  NOT NULL,
  role_id             UUID         NULL,
  permission_id       UUID         NULL,
  scope_type          VARCHAR(16)  NOT NULL,
  scope_id            UUID         NULL,
  granted_by_user_id  UUID         NOT NULL,
  status              BOOLEAN      NOT NULL DEFAULT true,
  create_at           TIMESTAMPTZ  NULL DEFAULT now(),
  update_at           TIMESTAMPTZ  NULL,
  CONSTRAINT sys_user_grant_pk PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_sys_user_grant_user_scope
  ON public.sys_user_grant (user_id, scope_type, scope_id);
CREATE INDEX IF NOT EXISTS ix_sys_user_grant_scope_type_id
  ON public.sys_user_grant (scope_type, scope_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_user_grant_user_role_scope
  ON public.sys_user_grant (user_id, grant_type, role_id, scope_type, scope_id)
  WHERE grant_type = 'role' AND role_id IS NOT NULL;

COMMENT ON TABLE public.sys_user_grant IS '用户授权 grant（RBAC+ABAC）';
COMMENT ON COLUMN public.sys_user_grant.id IS '主键';
COMMENT ON COLUMN public.sys_user_grant.user_id IS '用户 id';
COMMENT ON COLUMN public.sys_user_grant.grant_type IS 'role | direct_permission | tenant_admin';
COMMENT ON COLUMN public.sys_user_grant.role_id IS '逻辑引用 sys_role.id';
COMMENT ON COLUMN public.sys_user_grant.permission_id IS '逻辑引用 sys_permission.id';
COMMENT ON COLUMN public.sys_user_grant.scope_type IS '授权范围类型：platform/tenant/workspace';
COMMENT ON COLUMN public.sys_user_grant.scope_id IS '授权范围 id（tenant/workspace）';
COMMENT ON COLUMN public.sys_user_grant.granted_by_user_id IS '授权人用户 id';
COMMENT ON COLUMN public.sys_user_grant.status IS '状态';
COMMENT ON COLUMN public.sys_user_grant.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_user_grant.update_at IS '修改时间';
