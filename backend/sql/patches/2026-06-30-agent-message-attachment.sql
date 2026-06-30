CREATE TABLE IF NOT EXISTS public.agent_message_attachment (
  id            UUID         NOT NULL,
  workspace_id  UUID         NOT NULL,
  session_id    UUID         NOT NULL,
  message_id    UUID         NOT NULL,
  object_key    VARCHAR(1024) NOT NULL,
  storage_kind  VARCHAR(16)  NOT NULL,
  file_name     VARCHAR(256) NULL,
  content_type  VARCHAR(128) NULL,
  size          BIGINT       NULL,
  kind          VARCHAR(16)  NOT NULL,
  created_by    UUID         NULL,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
  CONSTRAINT agent_message_attachment_pk PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_agent_message_attachment_workspace_id ON public.agent_message_attachment (workspace_id);
CREATE INDEX IF NOT EXISTS ix_agent_message_attachment_session_id ON public.agent_message_attachment (session_id);
CREATE INDEX IF NOT EXISTS ix_agent_message_attachment_message_id ON public.agent_message_attachment (message_id);
COMMENT ON TABLE public.agent_message_attachment IS 'Agent 对话消息附件元数据（不含 download_url）';
COMMENT ON COLUMN public.agent_message_attachment.storage_kind IS '上传时快照: S3 / LOCAL / DEFAULT_LOCAL';
COMMENT ON COLUMN public.agent_message_attachment.kind IS 'image | file';
