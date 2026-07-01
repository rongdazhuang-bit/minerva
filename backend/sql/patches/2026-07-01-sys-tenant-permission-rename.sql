-- Rename sys_tenant_entitlement -> sys_tenant_permission; feature_code -> menu_id; granted_by_user_id -> create_by
-- Prerequisites: unified-permission-gateway P0 patch applied

ALTER TABLE public.sys_tenant_entitlement RENAME TO sys_tenant_permission;

ALTER TABLE public.sys_tenant_permission ADD COLUMN IF NOT EXISTS menu_id UUID NULL;

-- Map legacy feature_code rows to sys_menu.id via menu_key
UPDATE public.sys_tenant_permission tp
SET menu_id = m.id
FROM public.sys_menu m
WHERE tp.feature_code = 'feature:agent' AND m.menu_key = 'sub-agents';

UPDATE public.sys_tenant_permission tp
SET menu_id = m.id
FROM public.sys_menu m
WHERE tp.feature_code = 'feature:dataset' AND m.menu_key = 'sub-dataset';

UPDATE public.sys_tenant_permission tp
SET menu_id = m.id
FROM public.sys_menu m
WHERE tp.feature_code = 'feature:ocr' AND m.menu_key = 'sub-file-ocr';

UPDATE public.sys_tenant_permission tp
SET menu_id = m.id
FROM public.sys_menu m
WHERE tp.feature_code = 'feature:skills' AND m.menu_key = 'agents-skills';

UPDATE public.sys_tenant_permission tp
SET menu_id = m.id
FROM public.sys_menu m
WHERE tp.feature_code = 'feature:translate' AND m.menu_key = 'sub-doc-translate';

UPDATE public.sys_tenant_permission tp
SET menu_id = m.id
FROM public.sys_menu m
WHERE tp.feature_code = 'feature:rules' AND m.menu_key = 'sub-rules';

UPDATE public.sys_tenant_permission tp
SET menu_id = m.id
FROM public.sys_menu m
WHERE tp.feature_code = 'feature:file_storage' AND m.menu_key = 'settings-file-storage';

DELETE FROM public.sys_tenant_permission WHERE menu_id IS NULL;

ALTER TABLE public.sys_tenant_permission DROP COLUMN IF EXISTS feature_code;
ALTER TABLE public.sys_tenant_permission ALTER COLUMN menu_id SET NOT NULL;

ALTER TABLE public.sys_tenant_permission
  RENAME COLUMN granted_by_user_id TO create_by;

DROP INDEX IF EXISTS public.uq_sys_tenant_entitlement_tenant_feature;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_tenant_permission_tenant_menu
  ON public.sys_tenant_permission (tenant_id, menu_id);

COMMENT ON TABLE public.sys_tenant_permission IS '租户菜单开通（超管授权）';
COMMENT ON COLUMN public.sys_tenant_permission.menu_id IS '逻辑引用 sys_menu.id';
COMMENT ON COLUMN public.sys_tenant_permission.create_by IS '创建人用户 id';
