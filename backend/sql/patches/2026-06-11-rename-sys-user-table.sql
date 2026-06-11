-- 身份域表重命名：sys_users → sys_user
-- 使用: psql -U minerva -d minerva -f backend/sql/patches/2026-06-11-rename-sys-user-table.sql

ALTER TABLE IF EXISTS public.sys_users RENAME TO sys_user;
ALTER INDEX IF EXISTS public.ix_sys_users_email RENAME TO ix_sys_user_email;
ALTER INDEX IF EXISTS public.ix_users_email RENAME TO ix_sys_user_email;
ALTER INDEX IF EXISTS public.uq_sys_users_phone RENAME TO uq_sys_user_phone;
