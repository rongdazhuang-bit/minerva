-- GraphKB: drop per-graph llm/embedding columns (models live in Worker env only).
-- Patch: 2026-08-25-graph-kb-drop-model-columns.sql

ALTER TABLE public.graph_kb DROP COLUMN IF EXISTS llm_model;
ALTER TABLE public.graph_kb DROP COLUMN IF EXISTS llm_model_provider;
ALTER TABLE public.graph_kb DROP COLUMN IF EXISTS embedding_model;
ALTER TABLE public.graph_kb DROP COLUMN IF EXISTS embedding_model_provider;
