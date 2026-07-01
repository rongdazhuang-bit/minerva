-- Super-admin grants menu access to tenants
CREATE TABLE IF NOT EXISTS public.sys_tenant_permission (
  id         UUID         NOT NULL,
  tenant_id  UUID         NOT NULL,
  menu_id    UUID         NOT NULL,
  enabled    BOOLEAN      NOT NULL DEFAULT true,
  create_by  UUID         NOT NULL,
  create_at  TIMESTAMPTZ  NULL DEFAULT now(),
  update_at  TIMESTAMPTZ  NULL,
  CONSTRAINT sys_tenant_permission_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_tenant_permission_tenant_menu
  ON public.sys_tenant_permission (tenant_id, menu_id);
CREATE INDEX IF NOT EXISTS ix_sys_tenant_permission_tenant_id
  ON public.sys_tenant_permission (tenant_id);

COMMENT ON TABLE public.sys_tenant_permission IS '租户菜单开通（超管授权）';
COMMENT ON COLUMN public.sys_tenant_permission.id IS '主键';
COMMENT ON COLUMN public.sys_tenant_permission.tenant_id IS '所属 tenant';
COMMENT ON COLUMN public.sys_tenant_permission.menu_id IS '逻辑引用 sys_menu.id';
COMMENT ON COLUMN public.sys_tenant_permission.enabled IS '是否启用';
COMMENT ON COLUMN public.sys_tenant_permission.create_by IS '创建人用户 id';
COMMENT ON COLUMN public.sys_tenant_permission.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_tenant_permission.update_at IS '修改时间';
