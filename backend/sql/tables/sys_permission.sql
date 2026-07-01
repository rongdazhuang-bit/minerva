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
COMMENT ON TABLE public.sys_permission IS 'Platform permission catalog';
COMMENT ON COLUMN public.sys_permission.perm_code IS 'Globally unique permission code';
COMMENT ON COLUMN public.sys_permission.perm_type IS 'menu | api | data | feature';
COMMENT ON COLUMN public.sys_permission.menu_id IS 'Logical ref sys_menu.id when perm_type=menu';
