CREATE TABLE IF NOT EXISTS public.sys_user_role (
  id       UUID NOT NULL,
  user_id  UUID NOT NULL,
  role_id  UUID NOT NULL,
  CONSTRAINT sys_user_role_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_user_role_user_role
  ON public.sys_user_role (user_id, role_id);
CREATE INDEX IF NOT EXISTS ix_sys_user_role_user_id ON public.sys_user_role (user_id);
CREATE INDEX IF NOT EXISTS ix_sys_user_role_role_id ON public.sys_user_role (role_id);
COMMENT ON TABLE public.sys_user_role IS 'User to workspace sys_role mapping (app-enforced)';
