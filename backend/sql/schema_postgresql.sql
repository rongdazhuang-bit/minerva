-- Minerva 表结构（PostgreSQL），与 Alembic 迁移链一致：
-- 3552a1daa5cc (identity) -> … -> c3d4e5f6a7b8 (rule_base engineering_code) -> d4e5f6a7b8c9 (rule_config_prompt)
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



CREATE TABLE public.rule_base (
	id uuid NOT NULL,
	workspace_id uuid NOT NULL, -- 工作空间id
	sequence_number int2 DEFAULT 0 NOT NULL, -- 序号
    engineering_code varchar(64) NULL, -- 工程编码
	subject_code varchar(64) NULL, -- 专业
	serial_number varchar(32) NULL,
	document_type varchar(64) NULL, -- 文档类型
	review_section varchar(128) NOT NULL, -- 校审章节
	review_object varchar(128) NOT NULL, -- 校审对象
	review_rules text NOT NULL, -- 校审规则
	review_rules_ai text NULL, -- 校审规则（AI 润色）
	review_result text NOT NULL, -- 校审结果
	status varchar NOT NULL, -- 是有否有效(Y/N)
	create_at timestamptz NULL, -- 创建时间
	update_at timestamptz NULL, -- 更新时间
	CONSTRAINT rule_base_pk PRIMARY KEY (id),
	CONSTRAINT rule_base_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_rule_base_workspace_id ON public.rule_base (workspace_id);
COMMENT ON TABLE public.rule_base IS '规则库';
COMMENT ON COLUMN public.rule_base.workspace_id IS '工作空间id';
COMMENT ON COLUMN public.rule_base.sequence_number IS '序号';
COMMENT ON COLUMN public.rule_base.subject_code IS '专业';
COMMENT ON COLUMN public.rule_base.serial_number IS '编号';
COMMENT ON COLUMN public.rule_base.document_type IS '文档类型';
COMMENT ON COLUMN public.rule_base.engineering_code IS '工程编码';
COMMENT ON COLUMN public.rule_base.review_section IS '校审章节';
COMMENT ON COLUMN public.rule_base.review_object IS '校审对象';
COMMENT ON COLUMN public.rule_base.review_rules IS '校审规则';
COMMENT ON COLUMN public.rule_base.review_rules_ai IS '校审规则（AI 润色）';
COMMENT ON COLUMN public.rule_base.review_result IS '校审结果';
COMMENT ON COLUMN public.rule_base.status IS '是有否有效(Y/N)';
COMMENT ON COLUMN public.rule_base.create_at IS '创建时间';
COMMENT ON COLUMN public.rule_base.update_at IS '更新时间';


CREATE TABLE public.rule_config_prompt (
	id uuid NOT NULL,
	workspace_id uuid NOT NULL,
	model_id uuid NOT NULL,
	engineering_code varchar(64) NULL,
	subject_code varchar(64) NULL,
	document_type varchar(64) NULL,
	sys_prompt varchar(1024) NULL,
	user_prompt text NULL,
	chat_memory text NULL,
	create_at timestamptz NULL DEFAULT now(),
	update_at timestamptz NULL,
	CONSTRAINT rule_config_prompt_pkey PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_rule_config_prompt_workspace_id ON public.rule_config_prompt (workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_rule_config_prompt_workspace_scope ON public.rule_config_prompt (
	workspace_id,
	coalesce(engineering_code, ''),
	coalesce(subject_code, ''),
	coalesce(document_type, '')
);
COMMENT ON TABLE public.rule_config_prompt IS '规则库-提示词配置（按上下文绑定模型）';
COMMENT ON COLUMN public.rule_config_prompt.id IS 'id';
COMMENT ON COLUMN public.rule_config_prompt.workspace_id IS '工作空间id';
COMMENT ON COLUMN public.rule_config_prompt.model_id IS '模型id';
COMMENT ON COLUMN public.rule_config_prompt.engineering_code IS '工程编码';
COMMENT ON COLUMN public.rule_config_prompt.subject_code IS '专业';
COMMENT ON COLUMN public.rule_config_prompt.document_type IS '文档类型';
COMMENT ON COLUMN public.rule_config_prompt.sys_prompt IS '系统提示词';
COMMENT ON COLUMN public.rule_config_prompt.user_prompt IS '用户提示词';
COMMENT ON COLUMN public.rule_config_prompt.chat_memory IS '对话记忆';
COMMENT ON COLUMN public.rule_config_prompt.create_at IS '创建时间';
COMMENT ON COLUMN public.rule_config_prompt.update_at IS '更新时间';