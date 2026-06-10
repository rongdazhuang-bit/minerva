-- 将 rongda@yeah.net 设为平台超级管理员，并提升其在各租户/工作空间中的角色为 owner
-- 前置：用户须已注册（存在于 users 表）
-- 使用: psql -U minerva -d minerva -f backend/sql/patches/2026-06-10-users-super-admin.sql
--       psql -U minerva -d minerva -f backend/sql/seeds/super_admin_rongda.sql

UPDATE public.users
SET is_super_admin = true
WHERE lower(email) = lower('rongda@yeah.net');

UPDATE public.tenant_memberships tm
SET role = 'owner'::tenant_role
FROM public.users u
WHERE tm.user_id = u.id
  AND lower(u.email) = lower('rongda@yeah.net')
  AND tm.role = 'member'::tenant_role;

UPDATE public.workspace_memberships wm
SET role = 'owner'::workspace_role
FROM public.users u
WHERE wm.user_id = u.id
  AND lower(u.email) = lower('rongda@yeah.net')
  AND wm.role = 'member'::workspace_role;
