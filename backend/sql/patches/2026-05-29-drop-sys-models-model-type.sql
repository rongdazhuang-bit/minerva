UPDATE public.sys_models SET tags = CASE model_type
  WHEN 'text' THEN '["TEXT"]'::jsonb
  WHEN 'translate' THEN '["TRANSLATE"]'::jsonb
  WHEN 'embedding' THEN '["EMBEDDINGS"]'::jsonb
  WHEN 'rerank' THEN '["RERANKING"]'::jsonb
  ELSE tags
END;

ALTER TABLE public.sys_models DROP COLUMN IF EXISTS model_type;
