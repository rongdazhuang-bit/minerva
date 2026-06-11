-- 角色与全局 sys_menu 关联（无库级外键）
CREATE TABLE IF NOT EXISTS public.sys_role_menu (
  id       UUID NOT NULL,
  role_id  UUID NOT NULL,
  menu_id  UUID NOT NULL,
  CONSTRAINT sys_role_menu_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_role_menu_role_menu
  ON public.sys_role_menu (role_id, menu_id);
CREATE INDEX IF NOT EXISTS ix_sys_role_menu_role_id ON public.sys_role_menu (role_id);
CREATE INDEX IF NOT EXISTS ix_sys_role_menu_menu_id ON public.sys_role_menu (menu_id);
COMMENT ON TABLE public.sys_role_menu IS '角色菜单权限关联';
COMMENT ON COLUMN public.sys_role_menu.role_id IS 'sys_role.id';
COMMENT ON COLUMN public.sys_role_menu.menu_id IS '全局 sys_menu.id';
