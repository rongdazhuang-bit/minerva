-- Global permission catalog (RBAC + feature codes)
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
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_permission_perm_code
  ON public.sys_permission (perm_code);
CREATE INDEX IF NOT EXISTS ix_sys_permission_perm_type
  ON public.sys_permission (perm_type);
CREATE INDEX IF NOT EXISTS ix_sys_permission_menu_id
  ON public.sys_permission (menu_id);

COMMENT ON TABLE public.sys_permission IS '平台权限目录';
COMMENT ON COLUMN public.sys_permission.id IS '主键';
COMMENT ON COLUMN public.sys_permission.perm_code IS '权限码（全局唯一）';
COMMENT ON COLUMN public.sys_permission.perm_name IS '权限名称';
COMMENT ON COLUMN public.sys_permission.perm_type IS '权限类型：menu/api/data/feature';
COMMENT ON COLUMN public.sys_permission.resource_pattern IS 'ABAC 资源匹配模式';
COMMENT ON COLUMN public.sys_permission.menu_id IS '逻辑引用 sys_menu.id（menu 型权限）';
COMMENT ON COLUMN public.sys_permission.status IS '状态';
COMMENT ON COLUMN public.sys_permission.remark IS '备注';
COMMENT ON COLUMN public.sys_permission.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_permission.update_at IS '修改时间';
