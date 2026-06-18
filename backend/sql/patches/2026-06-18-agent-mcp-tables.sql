-- agent_mcp_client / agent_mcp_server（无库级外键）
CREATE TABLE IF NOT EXISTS public.agent_mcp_client (
  id            UUID         NOT NULL,
  workspace_id  UUID         NOT NULL,
  name          VARCHAR(128) NOT NULL,
  transport     VARCHAR(32)  NOT NULL,
  config        JSONB        NOT NULL DEFAULT '{}'::jsonb,
  secrets       JSONB        NOT NULL DEFAULT '{}'::jsonb,
  enabled       BOOLEAN      NOT NULL DEFAULT true,
  remark        VARCHAR(256) NULL,
  last_test_at  TIMESTAMPTZ  NULL,
  last_test_ok  BOOLEAN      NULL,
  create_at     TIMESTAMPTZ  NULL DEFAULT now(),
  update_at     TIMESTAMPTZ  NULL,
  CONSTRAINT agent_mcp_client_pk PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_agent_mcp_client_workspace_id
  ON public.agent_mcp_client (workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_mcp_client_workspace_name
  ON public.agent_mcp_client (workspace_id, name);

CREATE TABLE IF NOT EXISTS public.agent_mcp_server (
  id            UUID         NOT NULL,
  workspace_id  UUID         NOT NULL,
  name          VARCHAR(128) NOT NULL,
  slug          VARCHAR(64)  NOT NULL,
  enabled       BOOLEAN      NOT NULL DEFAULT true,
  exposure      JSONB        NOT NULL DEFAULT '{}'::jsonb,
  auth_type     VARCHAR(32)  NOT NULL DEFAULT 'NONE',
  auth_secret   VARCHAR(512) NULL,
  remark        VARCHAR(256) NULL,
  create_at     TIMESTAMPTZ  NULL DEFAULT now(),
  update_at     TIMESTAMPTZ  NULL,
  CONSTRAINT agent_mcp_server_pk PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_agent_mcp_server_workspace_id
  ON public.agent_mcp_server (workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_mcp_server_slug
  ON public.agent_mcp_server (slug);
