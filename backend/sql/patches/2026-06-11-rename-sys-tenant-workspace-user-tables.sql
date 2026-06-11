-- 身份域表重命名：sys_tenants / sys_tenant_memberships / sys_workspace_memberships
--   → sys_tenant / sys_tenant_user / sys_workspace_user
-- 使用: psql -U minerva -d minerva -f backend/sql/patches/2026-06-11-rename-sys-tenant-workspace-user-tables.sql

ALTER TABLE IF EXISTS public.sys_tenants RENAME TO sys_tenant;
ALTER INDEX IF EXISTS public.ix_sys_tenants_slug RENAME TO ix_sys_tenant_slug;

ALTER TABLE IF EXISTS public.sys_tenant_memberships RENAME TO sys_tenant_user;
ALTER INDEX IF EXISTS public.ix_sys_tenant_memberships_tenant_id
  RENAME TO ix_sys_tenant_user_tenant_id;
ALTER INDEX IF EXISTS public.ix_sys_tenant_memberships_user_id
  RENAME TO ix_sys_tenant_user_user_id;

ALTER TABLE IF EXISTS public.sys_workspace_memberships RENAME TO sys_workspace_user;
ALTER INDEX IF EXISTS public.ix_sys_workspace_memberships_user_id
  RENAME TO ix_sys_workspace_user_user_id;
ALTER INDEX IF EXISTS public.ix_sys_workspace_memberships_workspace_id
  RENAME TO ix_sys_workspace_user_workspace_id;

DO $$ BEGIN
  ALTER TABLE public.sys_tenant_user
    RENAME CONSTRAINT uq_sys_tenant_membership TO uq_sys_tenant_user;
EXCEPTION
  WHEN undefined_object THEN NULL;
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE public.sys_tenant_user
    RENAME CONSTRAINT uq_tenant_membership TO uq_sys_tenant_user;
EXCEPTION
  WHEN undefined_object THEN NULL;
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE public.sys_workspace_user
    RENAME CONSTRAINT uq_sys_workspace_membership TO uq_sys_workspace_user;
EXCEPTION
  WHEN undefined_object THEN NULL;
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE public.sys_workspace_user
    RENAME CONSTRAINT uq_workspace_membership TO uq_sys_workspace_user;
EXCEPTION
  WHEN undefined_object THEN NULL;
  WHEN duplicate_object THEN NULL;
END $$;
