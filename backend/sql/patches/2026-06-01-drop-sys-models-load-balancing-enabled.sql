-- backend/sql/patches/2026-06-01-drop-sys-models-load-balancing-enabled.sql
ALTER TABLE public.sys_models
  DROP COLUMN IF EXISTS load_balancing_enabled;
