-- P0: membership owner->admin enum rebuild + authorization tables
-- Apply: psql -U minerva -d minerva -f backend/sql/patches/2026-07-01-unified-permission-gateway-p0.sql

-- 1) Normalize legacy owner rows
UPDATE public.sys_workspace_user SET role = 'admin' WHERE role::text = 'owner';
UPDATE public.sys_tenant_user SET role = 'admin' WHERE role::text = 'owner';

-- 2) Rebuild tenant_role enum (admin, member only)
ALTER TYPE public.tenant_role RENAME TO tenant_role_old;
CREATE TYPE public.tenant_role AS ENUM ('admin', 'member');
ALTER TABLE public.sys_tenant_user
  ALTER COLUMN role TYPE public.tenant_role
  USING (
    CASE role::text
      WHEN 'owner' THEN 'admin'::public.tenant_role
      WHEN 'admin' THEN 'admin'::public.tenant_role
      ELSE 'member'::public.tenant_role
    END
  );
DROP TYPE public.tenant_role_old;

-- 3) Rebuild workspace_role enum (admin, member only)
ALTER TYPE public.workspace_role RENAME TO workspace_role_old;
CREATE TYPE public.workspace_role AS ENUM ('admin', 'member');
ALTER TABLE public.sys_workspace_user
  ALTER COLUMN role TYPE public.workspace_role
  USING (
    CASE role::text
      WHEN 'owner' THEN 'admin'::public.workspace_role
      WHEN 'admin' THEN 'admin'::public.workspace_role
      ELSE 'member'::public.workspace_role
    END
  );
DROP TYPE public.workspace_role_old;

-- 4) Authorization tables (see backend/sql/tables/sys_*.sql for canonical DDL)
CREATE TABLE IF NOT EXISTS public.sys_permission (
  id               UUID         NOT NULL,
  perm_code        VARCHAR(128) NOT NULL,
  perm_name        VARCHAR(128) NOT NULL,
  perm_type        VARCHAR(16)  NOT NULL,
  resource_pattern VARCHAR(256) NULL,
  menu_id          UUID         NULL,
  status           BOOLEAN      NOT NULL DEFAULT true,
  remark           VARCHAR(500) NULL,
  create_at        TIMESTAMPTZ  NULL DEFAULT now(),
  update_at        TIMESTAMPTZ  NULL,
  CONSTRAINT sys_permission_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_permission_perm_code ON public.sys_permission (perm_code);
CREATE INDEX IF NOT EXISTS ix_sys_permission_perm_type ON public.sys_permission (perm_type);
CREATE INDEX IF NOT EXISTS ix_sys_permission_menu_id ON public.sys_permission (menu_id);

CREATE TABLE IF NOT EXISTS public.sys_role_permission (
  id            UUID NOT NULL,
  role_id       UUID NOT NULL,
  permission_id UUID NOT NULL,
  CONSTRAINT sys_role_permission_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_role_permission_role_perm
  ON public.sys_role_permission (role_id, permission_id);
CREATE INDEX IF NOT EXISTS ix_sys_role_permission_role_id ON public.sys_role_permission (role_id);
CREATE INDEX IF NOT EXISTS ix_sys_role_permission_permission_id ON public.sys_role_permission (permission_id);

CREATE TABLE IF NOT EXISTS public.sys_tenant_entitlement (
  id                 UUID         NOT NULL,
  tenant_id          UUID         NOT NULL,
  feature_code       VARCHAR(64)  NOT NULL,
  enabled            BOOLEAN      NOT NULL DEFAULT true,
  granted_by_user_id UUID         NOT NULL,
  create_at          TIMESTAMPTZ  NULL DEFAULT now(),
  update_at          TIMESTAMPTZ  NULL,
  CONSTRAINT sys_tenant_entitlement_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_tenant_entitlement_tenant_feature
  ON public.sys_tenant_entitlement (tenant_id, feature_code);
CREATE INDEX IF NOT EXISTS ix_sys_tenant_entitlement_tenant_id ON public.sys_tenant_entitlement (tenant_id);

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
