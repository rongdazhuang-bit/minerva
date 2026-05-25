ALTER TABLE public.agent_run_node
  ADD COLUMN IF NOT EXISTS usage_json jsonb NULL;

COMMENT ON COLUMN public.agent_run_node.usage_json IS '该节点 LLM token 用量(JSONB，OpenAI 兼容 + 按需 details)';

ALTER TABLE public.agent_session
  ADD COLUMN IF NOT EXISTS usage_json jsonb NULL;

COMMENT ON COLUMN public.agent_session.usage_json IS '会话累计 token 用量(JSONB，含 by_phase)';
