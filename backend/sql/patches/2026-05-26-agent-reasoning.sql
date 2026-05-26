ALTER TABLE public.agent_run_node
  ADD COLUMN IF NOT EXISTS reasoning_text text NULL;

COMMENT ON COLUMN public.agent_run_node.reasoning_text IS '该 llm.round 节点 LLM 调用的思考全文';

ALTER TABLE public.agent_message
  ADD COLUMN IF NOT EXISTS reasoning_text text NULL;

COMMENT ON COLUMN public.agent_message.reasoning_text IS '助手消息对应的思考合并纯文本';
