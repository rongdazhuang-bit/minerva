-- 已有库增量：sys_tenants / sys_workspaces 扩展字段
ALTER TABLE public.sys_tenants
  ADD COLUMN IF NOT EXISTS status BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS remark VARCHAR(500) NULL,
  ADD COLUMN IF NOT EXISTS create_at TIMESTAMPTZ NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS update_at TIMESTAMPTZ NULL;

ALTER TABLE public.sys_workspaces
  ADD COLUMN IF NOT EXISTS status BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS remark VARCHAR(500) NULL,
  ADD COLUMN IF NOT EXISTS create_at TIMESTAMPTZ NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS update_at TIMESTAMPTZ NULL;

COMMENT ON COLUMN public.sys_tenants.status IS 'true=正常 false=停用';
COMMENT ON COLUMN public.sys_tenants.remark IS '备注';
COMMENT ON COLUMN public.sys_tenants.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_tenants.update_at IS '修改时间';
COMMENT ON COLUMN public.sys_workspaces.status IS 'true=正常 false=停用';
COMMENT ON COLUMN public.sys_workspaces.remark IS '备注';
COMMENT ON COLUMN public.sys_workspaces.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_workspaces.update_at IS '修改时间';
