-- GraphKB tables (无外键)
-- patch: 2026-08-23-graph-kb-tables.sql
-- 约定：不声明 FOREIGN KEY / REFERENCES / ON DELETE CASCADE；关联由应用层维护。

CREATE TABLE IF NOT EXISTS public.graph_kb (
  id                          UUID         NOT NULL DEFAULT gen_random_uuid(),
  workspace_id                UUID         NOT NULL,
  name                        VARCHAR(255) NOT NULL,
  description                 TEXT         NULL,
  engine                      VARCHAR(32)  NOT NULL,
  permission                  VARCHAR(64)  NOT NULL,
  llm_model                   VARCHAR(255) NULL,
  llm_model_provider          VARCHAR(255) NULL,
  embedding_model             VARCHAR(255) NULL,
  embedding_model_provider    VARCHAR(255) NULL,
  indexing_status             VARCHAR(32)  NOT NULL DEFAULT 'empty',
  created_by                  UUID         NOT NULL,
  updated_by                  UUID         NULL,
  create_at                   TIMESTAMPTZ  NULL DEFAULT now(),
  update_at                   TIMESTAMPTZ  NULL,
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_graph_kb_workspace_id ON public.graph_kb (workspace_id);
COMMENT ON TABLE public.graph_kb IS '图谱知识库主表（无外键；workspace_id 逻辑引用 sys_workspace）';
COMMENT ON COLUMN public.graph_kb.engine IS 'graphrag | lightrag；创建后不可改';
COMMENT ON COLUMN public.graph_kb.permission IS 'only_me | partial_members | all_team_members';
COMMENT ON COLUMN public.graph_kb.indexing_status IS 'empty | pending | running | completed | failed';
COMMENT ON COLUMN public.graph_kb.llm_model IS '逻辑绑定 sys_models Chat';
COMMENT ON COLUMN public.graph_kb.embedding_model IS '逻辑绑定 sys_models Embeddings';

CREATE TABLE IF NOT EXISTS public.graph_kb_member (
  id            UUID        NOT NULL DEFAULT gen_random_uuid(),
  workspace_id  UUID        NOT NULL,
  graph_id      UUID        NOT NULL,
  user_id       UUID        NOT NULL,
  created_by    UUID        NOT NULL,
  create_at     TIMESTAMPTZ NULL DEFAULT now(),
  PRIMARY KEY (id),
  CONSTRAINT uq_graph_kb_member_graph_user UNIQUE (graph_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_graph_kb_member_workspace_id ON public.graph_kb_member (workspace_id);
CREATE INDEX IF NOT EXISTS ix_graph_kb_member_graph_id ON public.graph_kb_member (graph_id);
COMMENT ON TABLE public.graph_kb_member IS 'partial_members 成员（无外键；graph_id 逻辑引用 graph_kb）';

CREATE TABLE IF NOT EXISTS public.graph_kb_document (
  id               UUID         NOT NULL DEFAULT gen_random_uuid(),
  workspace_id     UUID         NOT NULL,
  graph_id         UUID         NOT NULL,
  source_type      VARCHAR(32)  NOT NULL,
  name             VARCHAR(255) NOT NULL,
  storage_key      VARCHAR(1024) NULL,
  text_content     TEXT         NULL,
  mime_type        VARCHAR(128) NULL,
  size_bytes       INTEGER      NULL,
  indexing_status  VARCHAR(32)  NOT NULL DEFAULT 'pending',
  error            TEXT         NULL,
  created_by       UUID         NOT NULL,
  create_at        TIMESTAMPTZ  NULL DEFAULT now(),
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_graph_kb_document_workspace_id ON public.graph_kb_document (workspace_id);
CREATE INDEX IF NOT EXISTS ix_graph_kb_document_graph_id ON public.graph_kb_document (graph_id);
COMMENT ON TABLE public.graph_kb_document IS '图谱文档/纯文本源（无外键；graph_id 逻辑引用 graph_kb）';
COMMENT ON COLUMN public.graph_kb_document.source_type IS 'upload_file | plain_text';

CREATE TABLE IF NOT EXISTS public.graph_kb_job (
  id            UUID        NOT NULL DEFAULT gen_random_uuid(),
  workspace_id  UUID        NOT NULL,
  graph_id      UUID        NOT NULL,
  kind          VARCHAR(32) NOT NULL,
  status        VARCHAR(32) NOT NULL DEFAULT 'pending',
  error         TEXT        NULL,
  started_at    TIMESTAMPTZ NULL,
  finished_at   TIMESTAMPTZ NULL,
  created_by    UUID        NOT NULL,
  create_at     TIMESTAMPTZ NULL DEFAULT now(),
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_graph_kb_job_workspace_id ON public.graph_kb_job (workspace_id);
CREATE INDEX IF NOT EXISTS ix_graph_kb_job_graph_id ON public.graph_kb_job (graph_id);
COMMENT ON TABLE public.graph_kb_job IS '索引/清理任务（无外键；graph_id 逻辑引用 graph_kb）';
COMMENT ON COLUMN public.graph_kb_job.kind IS 'index | reindex | cleanup';

CREATE TABLE IF NOT EXISTS public.graph_kb_query (
  id            UUID        NOT NULL DEFAULT gen_random_uuid(),
  workspace_id  UUID        NOT NULL,
  graph_id      UUID        NOT NULL,
  query         TEXT        NOT NULL,
  mode          VARCHAR(32) NOT NULL,
  answer        TEXT        NULL,
  citations     JSONB       NULL,
  created_by    UUID        NOT NULL,
  create_at     TIMESTAMPTZ NULL DEFAULT now(),
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_graph_kb_query_workspace_id ON public.graph_kb_query (workspace_id);
CREATE INDEX IF NOT EXISTS ix_graph_kb_query_graph_id ON public.graph_kb_query (graph_id);
COMMENT ON TABLE public.graph_kb_query IS '菜单内问答历史（无外键；graph_id 逻辑引用 graph_kb）';
COMMENT ON COLUMN public.graph_kb_query.citations IS '引用实体/摘要 id（jsonb）';

CREATE TABLE IF NOT EXISTS public.graph_kb_entity (
  id                UUID         NOT NULL DEFAULT gen_random_uuid(),
  workspace_id      UUID         NOT NULL,
  graph_id          UUID         NOT NULL,
  engine_entity_id  VARCHAR(255) NOT NULL,
  name              VARCHAR(512) NOT NULL,
  entity_type       VARCHAR(255) NULL,
  description       TEXT         NULL,
  community_id      UUID         NULL,
  create_at         TIMESTAMPTZ  NULL DEFAULT now(),
  update_at         TIMESTAMPTZ  NULL,
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_graph_kb_entity_workspace_id ON public.graph_kb_entity (workspace_id);
CREATE INDEX IF NOT EXISTS ix_graph_kb_entity_graph_id ON public.graph_kb_entity (graph_id);
COMMENT ON TABLE public.graph_kb_entity IS '只读实体投影（无外键；graph_id 逻辑引用 graph_kb）';
COMMENT ON COLUMN public.graph_kb_entity.community_id IS '逻辑引用 graph_kb_community.id';

CREATE TABLE IF NOT EXISTS public.graph_kb_relation (
  id               UUID         NOT NULL DEFAULT gen_random_uuid(),
  workspace_id     UUID         NOT NULL,
  graph_id         UUID         NOT NULL,
  from_entity_id   VARCHAR(255) NOT NULL,
  to_entity_id     VARCHAR(255) NOT NULL,
  relation_type    VARCHAR(255) NULL,
  description      TEXT         NULL,
  weight           DOUBLE PRECISION NULL,
  create_at        TIMESTAMPTZ  NULL DEFAULT now(),
  update_at        TIMESTAMPTZ  NULL,
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_graph_kb_relation_workspace_id ON public.graph_kb_relation (workspace_id);
CREATE INDEX IF NOT EXISTS ix_graph_kb_relation_graph_id ON public.graph_kb_relation (graph_id);
COMMENT ON TABLE public.graph_kb_relation IS '只读关系投影（无外键；from/to 为引擎侧 entity id）';

CREATE TABLE IF NOT EXISTS public.graph_kb_community (
  id                   UUID         NOT NULL DEFAULT gen_random_uuid(),
  workspace_id         UUID         NOT NULL,
  graph_id             UUID         NOT NULL,
  engine_community_id  VARCHAR(255) NOT NULL,
  title                VARCHAR(512) NULL,
  summary              TEXT         NULL,
  level                INTEGER      NULL,
  parent_id            UUID         NULL,
  create_at            TIMESTAMPTZ  NULL DEFAULT now(),
  update_at            TIMESTAMPTZ  NULL,
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_graph_kb_community_workspace_id ON public.graph_kb_community (workspace_id);
CREATE INDEX IF NOT EXISTS ix_graph_kb_community_graph_id ON public.graph_kb_community (graph_id);
COMMENT ON TABLE public.graph_kb_community IS '只读社区/主题投影（无外键；parent_id 逻辑引用本表）';
