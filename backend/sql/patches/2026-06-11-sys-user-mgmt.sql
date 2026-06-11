-- 已有库增量：sys_users 档案扩展 + sys_user_role（无库级外键）

ALTER TABLE public.sys_users ADD COLUMN IF NOT EXISTS nickname VARCHAR(64);
ALTER TABLE public.sys_users ADD COLUMN IF NOT EXISTS phone VARCHAR(20);
ALTER TABLE public.sys_users ADD COLUMN IF NOT EXISTS status BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE public.sys_users ADD COLUMN IF NOT EXISTS remark VARCHAR(500);
ALTER TABLE public.sys_users ADD COLUMN IF NOT EXISTS department_item_id UUID;
ALTER TABLE public.sys_users ADD COLUMN IF NOT EXISTS update_at TIMESTAMPTZ;

UPDATE public.sys_users
SET nickname = split_part(email, '@', 1)
WHERE nickname IS NULL;

ALTER TABLE public.sys_users ALTER COLUMN nickname SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_users_phone
  ON public.sys_users (phone) WHERE phone IS NOT NULL;

COMMENT ON COLUMN public.sys_users.nickname IS 'Display name';
COMMENT ON COLUMN public.sys_users.phone IS 'Optional; globally unique when set';
COMMENT ON COLUMN public.sys_users.status IS 'true=active false=cannot login';
COMMENT ON COLUMN public.sys_users.remark IS 'Remark';
COMMENT ON COLUMN public.sys_users.department_item_id IS 'Logical ref sys_dict_item.id (SYS_DEPARTMENT)';
COMMENT ON COLUMN public.sys_users.update_at IS 'Last update time';

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
