-- File storage local path: add local_path column to sys_storage.
-- Idempotent; safe to run multiple times.

ALTER TABLE public.sys_storage
  ADD COLUMN IF NOT EXISTS local_path varchar(128) NULL;

COMMENT ON COLUMN public.sys_storage.local_path IS '本地存储根目录（相对 FILE_STORAGE_LOCAL_ROOT 或绝对路径）';
