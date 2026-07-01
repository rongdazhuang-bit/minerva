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
COMMENT ON TABLE public.sys_user_grant IS 'User authorization grants with ABAC scope';
COMMENT ON COLUMN public.sys_user_grant.grant_type IS 'role | direct_permission | tenant_admin';
