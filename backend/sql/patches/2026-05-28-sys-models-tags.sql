ALTER TABLE public.sys_models
  ADD COLUMN IF NOT EXISTS tags jsonb NOT NULL DEFAULT '["CHAT"]'::jsonb;

COMMENT ON COLUMN public.sys_models.tags IS '模型用途标签（MODEL_TAG 字典 code 数组）';

UPDATE public.sys_models
SET tags = '["CHAT"]'::jsonb
WHERE tags IS NULL;
