-- Minerva 表结构（PostgreSQL），与 Alembic 迁移链一致：
-- 3552a1daa5cc (identity) -> 947e36be8860 (rules) -> bbec5fe9111a (executions)
--
-- 使用: psql -U minerva -d minerva -f schema_postgresql.sql
-- 推荐仍用: cd backend && alembic upgrade head

DO $$ BEGIN
  CREATE TYPE tenant_role AS ENUM ('owner', 'admin', 'member');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE workspace_role AS ENUM ('owner', 'admin', 'member');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS tenants (
  id    UUID         NOT NULL,
  name  VARCHAR(200) NOT NULL,
  slug  VARCHAR(64)  NOT NULL,
  PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_tenants_slug ON tenants (slug);

CREATE TABLE IF NOT EXISTS users (
  id            UUID         NOT NULL,
  email         VARCHAR(320) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);

CREATE TABLE IF NOT EXISTS refresh_tokens (
  id         UUID         NOT NULL,
  user_id    UUID         NOT NULL,
  jti        UUID         NOT NULL,
  expires_at TIMESTAMPTZ  NOT NULL,
  revoked_at TIMESTAMPTZ  NULL,
  created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
  PRIMARY KEY (id),
  CONSTRAINT refresh_tokens_user_id_fk FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_refresh_tokens_jti ON refresh_tokens (jti);
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens (user_id);

CREATE TABLE IF NOT EXISTS tenant_memberships (
  id        UUID         NOT NULL,
  user_id   UUID         NOT NULL,
  tenant_id UUID         NOT NULL,
  role      tenant_role  NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_tenant_membership UNIQUE (user_id, tenant_id),
  CONSTRAINT tenant_memberships_user_id_fk FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT tenant_memberships_tenant_id_fk FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_tenant_memberships_tenant_id ON tenant_memberships (tenant_id);
CREATE INDEX IF NOT EXISTS ix_tenant_memberships_user_id ON tenant_memberships (user_id);

CREATE TABLE IF NOT EXISTS workspaces (
  id        UUID         NOT NULL,
  tenant_id UUID         NOT NULL,
  name      VARCHAR(200) NOT NULL,
  slug      VARCHAR(64)  NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_workspaces_tenant_slug UNIQUE (tenant_id, slug),
  CONSTRAINT workspaces_tenant_id_fk FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_workspaces_tenant_id ON workspaces (tenant_id);

CREATE TABLE IF NOT EXISTS workspace_memberships (
  id           UUID            NOT NULL,
  user_id      UUID            NOT NULL,
  workspace_id UUID            NOT NULL,
  role         workspace_role  NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_workspace_membership UNIQUE (user_id, workspace_id),
  CONSTRAINT workspace_memberships_user_id_fk FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT workspace_memberships_workspace_id_fk FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_workspace_memberships_user_id ON workspace_memberships (user_id);
CREATE INDEX IF NOT EXISTS ix_workspace_memberships_workspace_id ON workspace_memberships (workspace_id);


CREATE TABLE IF NOT EXISTS public.sys_ocr_tool (
  id UUID NOT NULL,
  workspace_id UUID NOT NULL,
  "name" VARCHAR(128) NOT NULL,
  url VARCHAR(128) NOT NULL,
  auth_type VARCHAR(64) NULL,
  user_name VARCHAR(64) NULL,
  user_passwd VARCHAR(128) NULL,
  api_key VARCHAR(128) NULL,
  remark VARCHAR(128) NULL,
  create_at TIMESTAMPTZ NULL DEFAULT now(),
  update_at TIMESTAMPTZ NULL,
  CONSTRAINT sys_ocr_tool_pk PRIMARY KEY (id),
  CONSTRAINT sys_ocr_tool_workspace_id_fk FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_sys_ocr_tool_workspace_id ON sys_ocr_tool (workspace_id);
COMMENT ON TABLE public.sys_ocr_tool IS 'OCR工具';
COMMENT ON COLUMN public.sys_ocr_tool.id IS 'id';
COMMENT ON COLUMN public.sys_ocr_tool.workspace_id IS '工作空间id';
COMMENT ON COLUMN public.sys_ocr_tool."name" IS '名称';
COMMENT ON COLUMN public.sys_ocr_tool.url IS '连接地址';
COMMENT ON COLUMN public.sys_ocr_tool.auth_type IS '认证方式';
COMMENT ON COLUMN public.sys_ocr_tool.user_name IS '账号';
COMMENT ON COLUMN public.sys_ocr_tool.user_passwd IS '密码';
COMMENT ON COLUMN public.sys_ocr_tool.api_key IS 'api key';
COMMENT ON COLUMN public.sys_ocr_tool.remark IS '备注';
COMMENT ON COLUMN public.sys_ocr_tool.create_at IS '创建日期';
COMMENT ON COLUMN public.sys_ocr_tool.update_at IS '更新日期';
