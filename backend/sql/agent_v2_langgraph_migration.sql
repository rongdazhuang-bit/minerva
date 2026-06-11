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
  CONSTRAINT agent_ltm_workspace_id_fk FOREIGN KEY (workspace_id) REFERENCES public.sys_workspaces (id) ON DELETE CASCADE,
  CONSTRAINT agent_ltm_session_id_fk FOREIGN KEY (session_id) REFERENCES public.agent_session (id) ON DELETE CASCADE,
  CONSTRAINT agent_ltm_source_run_id_fk FOREIGN KEY (source_run_id) REFERENCES public.agent_run (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_agent_ltm_workspace_id ON public.agent_long_term_memory (workspace_id);
CREATE INDEX IF NOT EXISTS ix_agent_ltm_session_id ON public.agent_long_term_memory (session_id);
CREATE INDEX IF NOT EXISTS ix_agent_ltm_workspace_session ON public.agent_long_term_memory (workspace_id, session_id);

-- LangGraph checkpoint: timestamps + indexes (requires tables from setup() or schema_postgresql.sql).
-- update_at on UPSERT is set in app code (MinervaAsyncPostgresSaver), not DB triggers.

ALTER TABLE public.checkpoints
  ADD COLUMN IF NOT EXISTS create_at timestamptz NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS update_at timestamptz NULL DEFAULT now();
ALTER TABLE public.checkpoint_blobs
  ADD COLUMN IF NOT EXISTS create_at timestamptz NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS update_at timestamptz NULL DEFAULT now();
ALTER TABLE public.checkpoint_writes
  ADD COLUMN IF NOT EXISTS create_at timestamptz NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS update_at timestamptz NULL DEFAULT now();

UPDATE public.checkpoints
SET create_at = COALESCE(create_at, now()), update_at = COALESCE(update_at, now())
WHERE create_at IS NULL OR update_at IS NULL;
UPDATE public.checkpoint_blobs
SET create_at = COALESCE(create_at, now()), update_at = COALESCE(update_at, now())
WHERE create_at IS NULL OR update_at IS NULL;
UPDATE public.checkpoint_writes
SET create_at = COALESCE(create_at, now()), update_at = COALESCE(update_at, now())
WHERE create_at IS NULL OR update_at IS NULL;

ALTER TABLE public.checkpoints
  ALTER COLUMN create_at SET NOT NULL,
  ALTER COLUMN update_at SET NOT NULL;
ALTER TABLE public.checkpoint_blobs
  ALTER COLUMN create_at SET NOT NULL,
  ALTER COLUMN update_at SET NOT NULL;
ALTER TABLE public.checkpoint_writes
  ALTER COLUMN create_at SET NOT NULL,
  ALTER COLUMN update_at SET NOT NULL;

ALTER TABLE public.checkpoint_writes
  ADD COLUMN IF NOT EXISTS task_path text NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS ix_checkpoints_create_at ON public.checkpoints (create_at);
CREATE INDEX IF NOT EXISTS ix_checkpoint_blobs_create_at ON public.checkpoint_blobs (create_at);
CREATE INDEX IF NOT EXISTS ix_checkpoint_writes_create_at ON public.checkpoint_writes (create_at);

DROP TRIGGER IF EXISTS trg_checkpoints_set_update_at ON public.checkpoints;
DROP TRIGGER IF EXISTS trg_checkpoint_blobs_set_update_at ON public.checkpoint_blobs;
DROP TRIGGER IF EXISTS trg_checkpoint_writes_set_update_at ON public.checkpoint_writes;
DROP FUNCTION IF EXISTS public.minerva_checkpoint_set_update_at();
