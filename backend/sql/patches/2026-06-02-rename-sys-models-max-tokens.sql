ALTER TABLE public.sys_models
  RENAME COLUMN max_tokens_to_sample TO max_tokens;

COMMENT ON COLUMN public.sys_models.max_tokens IS '最大 token 上限';
