-- Tenant-scoped RBAC role（无库级外键）
CREATE TABLE IF NOT EXISTS public.sys_role (
  id            UUID         NOT NULL,
  tenant_id     UUID         NOT NULL,
  workspace_id  UUID         NULL,
  role_name     VARCHAR(64)  NOT NULL,
  role_key      VARCHAR(64)  NOT NULL,
  role_sort     INT          NOT NULL DEFAULT 0,
  status        BOOLEAN      NOT NULL DEFAULT true,
  remark        VARCHAR(500) NULL,
  create_at     TIMESTAMPTZ  NULL DEFAULT now(),
  update_at     TIMESTAMPTZ  NULL,
  CONSTRAINT sys_role_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_role_tenant_role_key
  ON public.sys_role (tenant_id, role_key);
CREATE INDEX IF NOT EXISTS ix_sys_role_tenant_id ON public.sys_role (tenant_id);
CREATE INDEX IF NOT EXISTS ix_sys_role_workspace_id ON public.sys_role (workspace_id);
CREATE INDEX IF NOT EXISTS ix_sys_role_role_sort ON public.sys_role (role_sort);

COMMENT ON TABLE public.sys_role IS '租户作用域角色';
COMMENT ON COLUMN public.sys_role.id IS '主键';
COMMENT ON COLUMN public.sys_role.tenant_id IS '所属 tenant';
COMMENT ON COLUMN public.sys_role.workspace_id IS '所属 workspace；NULL 表示 tenant 内通用角色';
COMMENT ON COLUMN public.sys_role.role_name IS '角色名称';
COMMENT ON COLUMN public.sys_role.role_key IS '权限字符；tenant 内唯一';
COMMENT ON COLUMN public.sys_role.role_sort IS '显示顺序';
COMMENT ON COLUMN public.sys_role.status IS '是否启用';
COMMENT ON COLUMN public.sys_role.remark IS '备注';
COMMENT ON COLUMN public.sys_role.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_role.update_at IS '修改时间';
