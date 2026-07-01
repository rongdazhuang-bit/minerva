-- 系统全局菜单表（无库级外键）
CREATE TABLE IF NOT EXISTS public.sys_menu (
  id            UUID         NOT NULL,
  parent_id     UUID         NULL,
  menu_name     VARCHAR(64)  NOT NULL,
  i18n_key      VARCHAR(128) NULL,
  menu_key      VARCHAR(64)  NULL,
  order_num     INT          NOT NULL DEFAULT 0,
  path          VARCHAR(256) NULL,
  menu_type     CHAR(1)      NOT NULL,
  perms         VARCHAR(128) NULL,
  icon          VARCHAR(64)  NULL,
  visible       BOOLEAN      NOT NULL DEFAULT true,
  status        BOOLEAN      NOT NULL DEFAULT true,
  is_external   BOOLEAN      NOT NULL DEFAULT false,
  remark        VARCHAR(500) NULL,
  create_at     TIMESTAMPTZ  NULL DEFAULT now(),
  update_at     TIMESTAMPTZ  NULL,
  CONSTRAINT sys_menu_pk PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_sys_menu_parent_id ON public.sys_menu (parent_id);
CREATE INDEX IF NOT EXISTS ix_sys_menu_menu_type ON public.sys_menu (menu_type);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_menu_menu_key
  ON public.sys_menu (menu_key) WHERE menu_key IS NOT NULL;

COMMENT ON TABLE public.sys_menu IS '系统菜单（全局）';
COMMENT ON COLUMN public.sys_menu.id IS '主键';
COMMENT ON COLUMN public.sys_menu.parent_id IS '父菜单 id；NULL 为根';
COMMENT ON COLUMN public.sys_menu.menu_name IS '菜单名称';
COMMENT ON COLUMN public.sys_menu.i18n_key IS 'i18n 键';
COMMENT ON COLUMN public.sys_menu.menu_key IS '侧栏稳定键';
COMMENT ON COLUMN public.sys_menu.order_num IS '显示顺序';
COMMENT ON COLUMN public.sys_menu.path IS '路由地址';
COMMENT ON COLUMN public.sys_menu.menu_type IS 'M目录 C菜单 F按钮';
COMMENT ON COLUMN public.sys_menu.perms IS '权限标识';
COMMENT ON COLUMN public.sys_menu.icon IS 'Ant Design 图标名';
COMMENT ON COLUMN public.sys_menu.visible IS '是否在侧栏显示';
COMMENT ON COLUMN public.sys_menu.status IS '是否启用';
COMMENT ON COLUMN public.sys_menu.is_external IS '是否外链';
COMMENT ON COLUMN public.sys_menu.remark IS '备注';
COMMENT ON COLUMN public.sys_menu.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_menu.update_at IS '修改时间';
