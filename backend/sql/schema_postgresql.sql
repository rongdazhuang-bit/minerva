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
	ocr_type varchar(16) NULL,
	ocr_config text NULL,
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

CREATE TABLE public.sys_dict (
     id uuid NOT NULL,
     workspace_id uuid NOT NULL,
     dict_code varchar(64) NOT NULL,
     dict_name varchar(128) NULL,
     dict_sort int2 DEFAULT 0 NULL,
     create_at timestamptz NULL,
     update_at timestamptz NULL,
     CONSTRAINT sys_dict_pk PRIMARY KEY (id),
     CONSTRAINT uq_sys_dict_workspace_dict_code UNIQUE (workspace_id, dict_code),
     CONSTRAINT sys_dict_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE
);
COMMENT ON TABLE public.sys_dict IS '字典编码';

COMMENT ON COLUMN public.sys_dict.id IS 'uuid';
COMMENT ON COLUMN public.sys_dict.workspace_id IS '工作空间id';
COMMENT ON COLUMN public.sys_dict.dict_code IS '字典编码';
COMMENT ON COLUMN public.sys_dict.dict_name IS '字典名称';
COMMENT ON COLUMN public.sys_dict.dict_sort IS '排序';
COMMENT ON COLUMN public.sys_dict.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_dict.update_at IS '更新时间';

CREATE TABLE public.sys_dict_item (
  id uuid NOT NULL,
  dict_uuid uuid NOT NULL,
  parent_uuid uuid NULL,
  code varchar(64) NOT NULL,
  "name" varchar(64) NOT NULL,
  item_sort int2 DEFAULT 0 NULL,
  create_at timestamptz NULL,
  update_at timestamptz NULL,
  CONSTRAINT sys_dict_item_pk PRIMARY KEY (id),
  CONSTRAINT uq_sys_dict_item_dict_code UNIQUE (dict_uuid, code),
  CONSTRAINT sys_dict_item_dict_uuid_fkey FOREIGN KEY (dict_uuid) REFERENCES public.sys_dict(id) ON DELETE CASCADE,
  CONSTRAINT sys_dict_item_parent_uuid_fkey FOREIGN KEY (parent_uuid) REFERENCES public.sys_dict_item(id) ON DELETE RESTRICT
);
COMMENT ON TABLE public.sys_dict_item IS '字典明细';

COMMENT ON COLUMN public.sys_dict_item.id IS 'id';
COMMENT ON COLUMN public.sys_dict_item.dict_uuid IS 'sys_dict.id';
COMMENT ON COLUMN public.sys_dict_item.code IS '编码';
COMMENT ON COLUMN public.sys_dict_item."name" IS '姓名';
COMMENT ON COLUMN public.sys_dict_item.parent_uuid IS 'sys_dict_item.id';
COMMENT ON COLUMN public.sys_dict_item.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_dict_item.update_at IS '更新时间';
COMMENT ON COLUMN public.sys_dict_item.item_sort IS '排序';

CREATE TABLE public.sys_models (
	id uuid NOT NULL,
	workspace_id uuid NOT NULL,
	provider_name varchar(128) NOT NULL,
	model_name varchar(128) NOT NULL,
	model_type varchar(64) NOT NULL,
	enabled bool DEFAULT true NOT NULL,
	load_balancing_enabled bool DEFAULT false NOT NULL,
	auth_type varchar(64) NOT NULL,
	endpoint_url varchar(128) NULL,
	api_key varchar(128) NULL,
	auth_name varchar(64) NULL,
	auth_passwd varchar(128) NULL,
	context_size int2 NULL,
	max_tokens_to_sample int2 NULL,
	model_config text NULL,
	create_at timestamptz NULL,
	update_at timestamptz NULL,
	CONSTRAINT sys_models_pk PRIMARY KEY (id),
	CONSTRAINT sys_models_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_sys_models_workspace_id ON public.sys_models (workspace_id);
COMMENT ON TABLE public.sys_models IS '模型配置';

COMMENT ON COLUMN public.sys_models.id IS 'id';
COMMENT ON COLUMN public.sys_models.workspace_id IS '工作空间id';
COMMENT ON COLUMN public.sys_models.provider_name IS '模型供应商id';
COMMENT ON COLUMN public.sys_models.model_name IS '模型名称';
COMMENT ON COLUMN public.sys_models.model_type IS '模型类型';
COMMENT ON COLUMN public.sys_models.enabled IS '状态';
COMMENT ON COLUMN public.sys_models.load_balancing_enabled IS '负载均衡';
COMMENT ON COLUMN public.sys_models.auth_type IS '认证方式';
COMMENT ON COLUMN public.sys_models.endpoint_url IS '模型地址';
COMMENT ON COLUMN public.sys_models.api_key IS 'api key';
COMMENT ON COLUMN public.sys_models.auth_name IS '账号';
COMMENT ON COLUMN public.sys_models.auth_passwd IS '密码';
COMMENT ON COLUMN public.sys_models.context_size IS '上下文窗口大小';
COMMENT ON COLUMN public.sys_models.max_tokens_to_sample IS '最大 token 上限';
COMMENT ON COLUMN public.sys_models.model_config IS '其它配置项';
COMMENT ON COLUMN public.sys_models.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_models.update_at IS '更新时间';

CREATE TABLE public.ocr_file (
	id uuid NOT NULL,
	workspace_id uuid NOT NULL,
	file_name varchar(256) NULL,
	file_size int8 NULL,
	object_key varchar(1024) NOT NULL,
	ocr_type varchar(16) NOT NULL,
	status varchar(16) NOT NULL,
	page_count int4 NULL,
	remark text NULL,
	create_at timestamptz NULL,
	update_at timestamptz NULL,
	CONSTRAINT ocr_file_pk PRIMARY KEY (id)
);

COMMENT ON TABLE public.ocr_file IS 'OCR文件';
COMMENT ON COLUMN public.ocr_file.id IS 'id';
COMMENT ON COLUMN public.ocr_file.workspace_id IS '工作空间id';
COMMENT ON COLUMN public.ocr_file.file_name IS '源文件名';
COMMENT ON COLUMN public.ocr_file.file_size IS '文件大小(字节)';
COMMENT ON COLUMN public.ocr_file.object_key IS '文件对象键';
COMMENT ON COLUMN public.ocr_file.ocr_type IS 'OCR类型';
COMMENT ON COLUMN public.ocr_file.status IS '状态(字典OCR_FILE_STATUS)';
COMMENT ON COLUMN public.ocr_file.page_count IS '页数';
COMMENT ON COLUMN public.ocr_file.remark IS '备注';
COMMENT ON COLUMN public.ocr_file.create_at IS '创建时间';
COMMENT ON COLUMN public.ocr_file.update_at IS '更新时间';

CREATE TABLE public.sys_storage (
	id uuid NOT NULL,
	workspace_id uuid NOT NULL,
	"name" varchar(32) NULL,
	"type" varchar(16) NULL,
	enabled bool DEFAULT true NOT NULL,
	auth_type varchar(64) NOT NULL,
	endpoint_url varchar(128) NULL,
	api_key varchar(128) NULL,
	auth_name varchar(64) NULL,
	auth_passwd varchar(128) NULL,
	create_at timestamptz NULL,
	update_at timestamptz NULL,
	CONSTRAINT sys_store_pk PRIMARY KEY (id)
);

COMMENT ON TABLE public.sys_storage IS '文件存储';
COMMENT ON COLUMN public.sys_storage.id IS 'id';
COMMENT ON COLUMN public.sys_storage.workspace_id IS '工作空间id';
COMMENT ON COLUMN public.sys_storage."name" IS '名称';
COMMENT ON COLUMN public.sys_storage."type" IS '存储类型';
COMMENT ON COLUMN public.sys_storage.enabled IS '状态';
COMMENT ON COLUMN public.sys_storage.auth_type IS '认证方式';
COMMENT ON COLUMN public.sys_storage.endpoint_url IS '地址';
COMMENT ON COLUMN public.sys_storage.api_key IS 'api key';
COMMENT ON COLUMN public.sys_storage.auth_name IS '账号';
COMMENT ON COLUMN public.sys_storage.auth_passwd IS '密码';
COMMENT ON COLUMN public.sys_storage.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_storage.update_at IS '更新时间';

CREATE TABLE IF NOT EXISTS public.sys_celery (
  id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  "name" varchar(64) NOT NULL,
  cron varchar(64) NULL,
  status varchar(2) NULL,
  task varchar(128) NULL,
  remark varchar(128) NULL,
  create_at timestamptz NULL,
  update_at timestamptz NULL,
  CONSTRAINT sys_tasks_pk PRIMARY KEY (id)
);
ALTER TABLE public.sys_celery
  ADD COLUMN IF NOT EXISTS task_code varchar(64),
  ADD COLUMN IF NOT EXISTS args_json jsonb,
  ADD COLUMN IF NOT EXISTS kwargs_json jsonb,
  ADD COLUMN IF NOT EXISTS timezone varchar(64),
  ADD COLUMN IF NOT EXISTS enabled bool,
  ADD COLUMN IF NOT EXISTS next_run_at timestamptz,
  ADD COLUMN IF NOT EXISTS last_run_at timestamptz,
  ADD COLUMN IF NOT EXISTS last_status varchar(32),
  ADD COLUMN IF NOT EXISTS last_error text,
  ADD COLUMN IF NOT EXISTS version bigint;
ALTER TABLE public.sys_celery
  ALTER COLUMN task_code TYPE varchar(64),
  ALTER COLUMN args_json TYPE jsonb USING
    CASE
      WHEN args_json IS NULL THEN NULL
      WHEN btrim(args_json::text, '"') = '' THEN NULL
      ELSE (args_json::text)::jsonb
    END,
  ALTER COLUMN kwargs_json TYPE jsonb USING
    CASE
      WHEN kwargs_json IS NULL THEN NULL
      WHEN btrim(kwargs_json::text, '"') = '' THEN NULL
      ELSE (kwargs_json::text)::jsonb
    END,
  ALTER COLUMN timezone TYPE varchar(64),
  ALTER COLUMN timezone SET DEFAULT 'Asia/Shanghai',
  ALTER COLUMN enabled SET DEFAULT true,
  ALTER COLUMN version TYPE bigint,
  ALTER COLUMN version SET DEFAULT 0;
UPDATE public.sys_celery
SET enabled = true
WHERE enabled IS NULL;
UPDATE public.sys_celery
SET version = 0
WHERE version IS NULL;
ALTER TABLE public.sys_celery
  ALTER COLUMN enabled SET NOT NULL,
  ALTER COLUMN version SET NOT NULL;
UPDATE public.sys_celery
SET task = ''
WHERE task IS NULL;
ALTER TABLE public.sys_celery
  ALTER COLUMN task SET NOT NULL;
UPDATE public.sys_celery
SET task_code = LEFT(task, 64)
WHERE task_code IS NULL AND task IS NOT NULL;
UPDATE public.sys_celery
SET task_code = LEFT(id::text, 64)
WHERE task_code IS NULL;
ALTER TABLE public.sys_celery
  ALTER COLUMN task_code SET NOT NULL;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'sys_celery_workspace_id_fk'
      AND conrelid = 'public.sys_celery'::regclass
  ) THEN
    ALTER TABLE public.sys_celery
      ADD CONSTRAINT sys_celery_workspace_id_fk
      FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;
  END IF;
END $$;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'uq_sys_celery_workspace_task_code'
      AND conrelid = 'public.sys_celery'::regclass
  ) THEN
    ALTER TABLE public.sys_celery
      ADD CONSTRAINT uq_sys_celery_workspace_task_code UNIQUE (workspace_id, task_code);
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_sys_celery_workspace_id ON public.sys_celery (workspace_id);
CREATE INDEX IF NOT EXISTS ix_sys_celery_workspace_enabled ON public.sys_celery (workspace_id, enabled);
CREATE INDEX IF NOT EXISTS ix_sys_celery_enabled_update_at ON public.sys_celery (enabled, update_at);
COMMENT ON TABLE public.sys_celery IS '定时任务调度';
COMMENT ON COLUMN public.sys_celery.id IS 'id';
COMMENT ON COLUMN public.sys_celery.workspace_id IS '工作空间id';
COMMENT ON COLUMN public.sys_celery."name" IS '名称';
COMMENT ON COLUMN public.sys_celery.task_code IS '任务编码';
COMMENT ON COLUMN public.sys_celery.cron IS 'cron';
COMMENT ON COLUMN public.sys_celery.task IS '任务';
COMMENT ON COLUMN public.sys_celery.args_json IS '位置参数(JSONB)';
COMMENT ON COLUMN public.sys_celery.kwargs_json IS '关键字参数(JSONB)';
COMMENT ON COLUMN public.sys_celery.timezone IS '时区';
COMMENT ON COLUMN public.sys_celery.enabled IS '是否启用';
COMMENT ON COLUMN public.sys_celery.next_run_at IS '下次执行时间';
COMMENT ON COLUMN public.sys_celery.last_run_at IS '上次执行时间';
COMMENT ON COLUMN public.sys_celery.last_status IS '上次执行状态';
COMMENT ON COLUMN public.sys_celery.last_error IS '上次错误';
COMMENT ON COLUMN public.sys_celery.version IS '版本号';
COMMENT ON COLUMN public.sys_celery.status IS '状态(Y/N)';
COMMENT ON COLUMN public.sys_celery.remark IS '备注';
COMMENT ON COLUMN public.sys_celery.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_celery.update_at IS '更新时间';

