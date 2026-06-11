-- 已有库增量：workspace 角色表 sys_role + sys_role_menu（无库级外键）
CREATE TABLE IF NOT EXISTS public.sys_role (
  id            UUID         NOT NULL,
  workspace_id  UUID         NOT NULL,
  role_name     VARCHAR(64)  NOT NULL,
  role_key      VARCHAR(64)  NOT NULL,
  role_sort     INT          NOT NULL DEFAULT 0,
  status        BOOLEAN      NOT NULL DEFAULT true,
  remark        VARCHAR(500) NULL,
  create_at     TIMESTAMPTZ  NULL DEFAULT now(),
  update_at     TIMESTAMPTZ  NULL,
  CONSTRAINT sys_role_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_role_workspace_role_key
  ON public.sys_role (workspace_id, role_key);
CREATE INDEX IF NOT EXISTS ix_sys_role_workspace_id ON public.sys_role (workspace_id);
CREATE INDEX IF NOT EXISTS ix_sys_role_role_sort ON public.sys_role (role_sort);

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
