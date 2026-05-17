-- Agent v2 (LangGraph): additive migration for existing databases.
-- Apply after backup. Fresh installs should use updated schema_postgresql.sql instead.

ALTER TABLE public.agent_session
  ADD COLUMN IF NOT EXISTS summary_text text NULL;

ALTER TABLE public.agent_message
  ADD COLUMN IF NOT EXISTS message_json jsonb NULL;

CREATE TABLE IF NOT EXISTS public.agent_plan (
  id uuid NOT NULL,
  run_id uuid NOT NULL,
  steps_json jsonb NOT NULL,
  status varchar(16) NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id),
  CONSTRAINT agent_plan_run_id_fk FOREIGN KEY (run_id) REFERENCES public.agent_run (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_agent_plan_run_id ON public.agent_plan (run_id);

CREATE TABLE IF NOT EXISTS public.agent_long_term_memory (
  id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  session_id uuid NULL,
  kind varchar(32) NOT NULL,
  key varchar(128) NULL,
  content text NOT NULL,
  tags jsonb NULL,
  source_run_id uuid NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NULL,
  PRIMARY KEY (id),
  CONSTRAINT agent_ltm_workspace_id_fk FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id) ON DELETE CASCADE,
  CONSTRAINT agent_ltm_session_id_fk FOREIGN KEY (session_id) REFERENCES public.agent_session (id) ON DELETE CASCADE,
  CONSTRAINT agent_ltm_source_run_id_fk FOREIGN KEY (source_run_id) REFERENCES public.agent_run (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_agent_ltm_workspace_id ON public.agent_long_term_memory (workspace_id);
CREATE INDEX IF NOT EXISTS ix_agent_ltm_session_id ON public.agent_long_term_memory (session_id);
CREATE INDEX IF NOT EXISTS ix_agent_ltm_workspace_session ON public.agent_long_term_memory (workspace_id, session_id);
