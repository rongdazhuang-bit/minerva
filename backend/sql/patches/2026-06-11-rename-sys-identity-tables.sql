-- 身份域表重命名：tenants/users/memberships/workspaces → sys_* 前缀
-- 使用: psql -U minerva -d minerva -f backend/sql/patches/2026-06-11-rename-sys-identity-tables.sql

ALTER TABLE IF EXISTS public.tenants RENAME TO sys_tenants;
ALTER INDEX IF EXISTS public.ix_tenants_slug RENAME TO ix_sys_tenants_slug;

ALTER TABLE IF EXISTS public.users RENAME TO sys_users;
ALTER INDEX IF EXISTS public.ix_users_email RENAME TO ix_sys_users_email;

ALTER TABLE IF EXISTS public.tenant_memberships RENAME TO sys_tenant_memberships;
ALTER INDEX IF EXISTS public.ix_tenant_memberships_tenant_id RENAME TO ix_sys_tenant_memberships_tenant_id;
ALTER INDEX IF EXISTS public.ix_tenant_memberships_user_id RENAME TO ix_sys_tenant_memberships_user_id;

ALTER TABLE IF EXISTS public.workspaces RENAME TO sys_workspaces;
ALTER INDEX IF EXISTS public.ix_workspaces_tenant_id RENAME TO ix_sys_workspaces_tenant_id;

ALTER TABLE IF EXISTS public.workspace_memberships RENAME TO sys_workspace_memberships;
ALTER INDEX IF EXISTS public.ix_workspace_memberships_user_id RENAME TO ix_sys_workspace_memberships_user_id;
ALTER INDEX IF EXISTS public.ix_workspace_memberships_workspace_id RENAME TO ix_sys_workspace_memberships_workspace_id;

DO $$ BEGIN
  ALTER TABLE public.sys_tenant_memberships
    RENAME CONSTRAINT uq_tenant_membership TO uq_sys_tenant_membership;
EXCEPTION
  WHEN undefined_object THEN NULL;
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE public.sys_workspaces
    RENAME CONSTRAINT uq_workspaces_tenant_slug TO uq_sys_workspaces_tenant_slug;
EXCEPTION
  WHEN undefined_object THEN NULL;
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE public.sys_workspace_memberships
    RENAME CONSTRAINT uq_workspace_membership TO uq_sys_workspace_membership;
EXCEPTION
  WHEN undefined_object THEN NULL;
  WHEN duplicate_object THEN NULL;
END $$;
