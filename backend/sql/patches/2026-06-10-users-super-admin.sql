-- 平台超级管理员标记（users.is_super_admin）
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS is_super_admin BOOLEAN NOT NULL DEFAULT false;
COMMENT ON COLUMN public.users.is_super_admin IS '平台超级管理员；可管理全局菜单等系统能力';
