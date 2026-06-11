-- 平台超级管理员标记（sys_users.is_super_admin）
-- 已有库若仍为 users 表，请先执行 2026-06-11-rename-sys-identity-tables.sql
ALTER TABLE public.sys_users
  ADD COLUMN IF NOT EXISTS is_super_admin BOOLEAN NOT NULL DEFAULT false;
COMMENT ON COLUMN public.sys_users.is_super_admin IS '平台超级管理员；可管理全局菜单等系统能力';
