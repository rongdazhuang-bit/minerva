-- 已有库增量：系统全局菜单表 sys_menu（无库级外键）
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
