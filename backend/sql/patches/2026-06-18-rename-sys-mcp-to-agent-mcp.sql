-- MCP 表重命名：sys_mcp_* → agent_mcp_*
-- 使用: psql -U minerva -d minerva -f backend/sql/patches/2026-06-18-rename-sys-mcp-to-agent-mcp.sql

ALTER TABLE IF EXISTS public.sys_mcp_client RENAME TO agent_mcp_client;
ALTER INDEX IF EXISTS public.ix_sys_mcp_client_workspace_id RENAME TO ix_agent_mcp_client_workspace_id;
ALTER INDEX IF EXISTS public.uq_sys_mcp_client_workspace_name RENAME TO uq_agent_mcp_client_workspace_name;

DO $$ BEGIN
  ALTER TABLE public.agent_mcp_client
    RENAME CONSTRAINT sys_mcp_client_pk TO agent_mcp_client_pk;
EXCEPTION
  WHEN undefined_object THEN NULL;
  WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE IF EXISTS public.sys_mcp_server RENAME TO agent_mcp_server;
ALTER INDEX IF EXISTS public.ix_sys_mcp_server_workspace_id RENAME TO ix_agent_mcp_server_workspace_id;
ALTER INDEX IF EXISTS public.uq_sys_mcp_server_slug RENAME TO uq_agent_mcp_server_slug;

DO $$ BEGIN
  ALTER TABLE public.agent_mcp_server
    RENAME CONSTRAINT sys_mcp_server_pk TO agent_mcp_server_pk;
EXCEPTION
  WHEN undefined_object THEN NULL;
  WHEN duplicate_object THEN NULL;
END $$;
