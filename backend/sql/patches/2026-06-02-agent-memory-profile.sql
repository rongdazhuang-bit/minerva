-- Persistent workspace/session memory profiles (mem0 backend only; no FK).
CREATE TABLE IF NOT EXISTS public.agent_memory_profile (
  id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  session_id uuid NULL,
  profile_text text NOT NULL DEFAULT '',
  updated_by uuid NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_agent_memory_profile_workspace
  ON public.agent_memory_profile (workspace_id);
CREATE INDEX IF NOT EXISTS ix_agent_memory_profile_workspace_session
  ON public.agent_memory_profile (workspace_id, session_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_memory_profile_workspace_null_session
  ON public.agent_memory_profile (workspace_id) WHERE session_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_memory_profile_workspace_session
  ON public.agent_memory_profile (workspace_id, session_id) WHERE session_id IS NOT NULL;
COMMENT ON TABLE public.agent_memory_profile IS 'Agent 持久人物画像（mem0 模式；工作区/会话级）';
