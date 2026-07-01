-- Maps workspace/tenant roles to sys_permission rows (replaces sys_role_menu long-term)
CREATE TABLE IF NOT EXISTS public.sys_role_permission (
  id            UUID NOT NULL,
  role_id       UUID NOT NULL,
  permission_id UUID NOT NULL,
  CONSTRAINT sys_role_permission_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_role_permission_role_perm
  ON public.sys_role_permission (role_id, permission_id);
CREATE INDEX IF NOT EXISTS ix_sys_role_permission_role_id
  ON public.sys_role_permission (role_id);
CREATE INDEX IF NOT EXISTS ix_sys_role_permission_permission_id
  ON public.sys_role_permission (permission_id);
COMMENT ON TABLE public.sys_role_permission IS 'Role to permission mapping (app-enforced)';
