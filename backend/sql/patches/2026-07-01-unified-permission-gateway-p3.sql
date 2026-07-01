-- P3: sys_role tenant scope + permission migration + drop legacy tables
-- Prerequisites: P0 + P2 patches applied
-- Apply: psql -U minerva -d minerva -f backend/sql/patches/2026-07-01-unified-permission-gateway-p3.sql

-- 1) sys_role: add tenant_id, make workspace_id nullable, rebuild unique index
ALTER TABLE public.sys_role ADD COLUMN IF NOT EXISTS tenant_id UUID NULL;

UPDATE public.sys_role r
SET tenant_id = w.tenant_id
FROM public.sys_workspaces w
WHERE r.workspace_id = w.id
  AND r.tenant_id IS NULL;

UPDATE public.sys_role
SET tenant_id = (
  SELECT t.id FROM public.sys_tenant t ORDER BY t.create_at NULLS LAST LIMIT 1
)
WHERE tenant_id IS NULL;

ALTER TABLE public.sys_role ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE public.sys_role ALTER COLUMN workspace_id DROP NOT NULL;

DROP INDEX IF EXISTS public.uq_sys_role_workspace_role_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_role_tenant_role_key
  ON public.sys_role (tenant_id, role_key);
CREATE INDEX IF NOT EXISTS ix_sys_role_tenant_id ON public.sys_role (tenant_id);

COMMENT ON COLUMN public.sys_role.tenant_id IS '所属 tenant';
COMMENT ON COLUMN public.sys_role.workspace_id IS '所属 workspace；NULL 表示 tenant 内通用角色';

-- 2) Seed sys_permission from sys_menu (menu / button permissions)
INSERT INTO public.sys_permission (
  id,
  perm_code,
  perm_name,
  perm_type,
  menu_id,
  status,
  create_at
)
SELECT
  gen_random_uuid(),
  COALESCE(
    NULLIF(TRIM(m.perms), ''),
    'menu:' || COALESCE(NULLIF(TRIM(m.menu_key), ''), m.id::text)
  ),
  m.menu_name,
  CASE WHEN m.menu_type = 'F' THEN 'api' ELSE 'menu' END,
  m.id,
  m.status,
  COALESCE(m.create_at, now())
FROM public.sys_menu m
WHERE NOT EXISTS (
  SELECT 1 FROM public.sys_permission p WHERE p.menu_id = m.id
);

-- 3) Seed platform feature + tenant manage permission codes
INSERT INTO public.sys_permission (id, perm_code, perm_name, perm_type, status, create_at)
SELECT gen_random_uuid(), v.perm_code, v.perm_name, v.perm_type, true, now()
FROM (
  VALUES
    ('feature:agent', 'Agent 模块', 'feature'),
    ('feature:dataset', '知识库模块', 'feature'),
    ('feature:ocr', 'OCR 模块', 'feature'),
    ('feature:skills', 'Skills 模块', 'feature'),
    ('feature:translate', '翻译模块', 'feature'),
    ('feature:rules', '规则模块', 'feature'),
    ('feature:file_storage', '文件存储模块', 'feature'),
    ('tenant:member:manage', '租户成员管理', 'api'),
    ('tenant:role:manage', '租户角色管理', 'api'),
    ('workspace:manage', '工作空间管理', 'api'),
    ('platform:tenant:manage', '平台租户管理', 'api')
) AS v(perm_code, perm_name, perm_type)
WHERE NOT EXISTS (
  SELECT 1 FROM public.sys_permission p WHERE p.perm_code = v.perm_code
);

-- 4) Migrate sys_role_menu -> sys_role_permission
INSERT INTO public.sys_role_permission (id, role_id, permission_id)
SELECT gen_random_uuid(), rm.role_id, p.id
FROM public.sys_role_menu rm
JOIN public.sys_permission p ON p.menu_id = rm.menu_id
WHERE NOT EXISTS (
  SELECT 1
  FROM public.sys_role_permission rp
  WHERE rp.role_id = rm.role_id
    AND rp.permission_id = p.id
);

-- 5) Drop legacy tables (data must live in sys_user_grant + sys_role_permission)
DROP TABLE IF EXISTS public.sys_user_role;
DROP TABLE IF EXISTS public.sys_role_menu;
