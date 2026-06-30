-- Minerva 表结构（PostgreSQL）
--
-- 约定：不在库层声明 FOREIGN KEY；表间关联由应用层删除/校验维护。
-- 已有库若含历史外键，可执行: psql -f backend/sql/patches/drop-foreign-keys.sql
--
-- 使用: psql -U minerva -d minerva -f schema_postgresql.sql

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

CREATE TABLE IF NOT EXISTS sys_tenant (
  id        UUID         NOT NULL,
  name      VARCHAR(200) NOT NULL,
  slug      VARCHAR(64)  NOT NULL,
  status    BOOLEAN      NOT NULL DEFAULT true,
  remark    VARCHAR(500) NULL,
  create_at TIMESTAMPTZ  NULL DEFAULT now(),
  update_at TIMESTAMPTZ  NULL,
  PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_sys_tenant_slug ON sys_tenant (slug);
COMMENT ON COLUMN public.sys_tenant.status IS 'true=正常 false=停用';
COMMENT ON COLUMN public.sys_tenant.remark IS '备注';
COMMENT ON COLUMN public.sys_tenant.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_tenant.update_at IS '修改时间';

CREATE TABLE IF NOT EXISTS sys_user (
  id                  UUID         NOT NULL,
  email               VARCHAR(320) NOT NULL,
  password_hash       VARCHAR(255) NOT NULL,
  is_super_admin      BOOLEAN      NOT NULL DEFAULT false,
  nickname            VARCHAR(64)  NOT NULL,
  phone               VARCHAR(20)  NULL,
  status              BOOLEAN      NOT NULL DEFAULT true,
  remark              VARCHAR(500) NULL,
  department_item_id  UUID         NULL,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
  update_at           TIMESTAMPTZ  NULL,
  PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_sys_user_email ON sys_user (email);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_user_phone ON sys_user (phone) WHERE phone IS NOT NULL;
COMMENT ON COLUMN public.sys_user.nickname IS 'Display name';
COMMENT ON COLUMN public.sys_user.phone IS 'Optional; globally unique when set';
COMMENT ON COLUMN public.sys_user.status IS 'true=active false=cannot login';
COMMENT ON COLUMN public.sys_user.department_item_id IS 'Logical ref sys_dict_item.id (SYS_DEPARTMENT)';

CREATE TABLE IF NOT EXISTS public.sys_user_role (
  id       UUID NOT NULL,
  user_id  UUID NOT NULL,
  role_id  UUID NOT NULL,
  CONSTRAINT sys_user_role_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_user_role_user_role
  ON public.sys_user_role (user_id, role_id);
CREATE INDEX IF NOT EXISTS ix_sys_user_role_user_id ON public.sys_user_role (user_id);
CREATE INDEX IF NOT EXISTS ix_sys_user_role_role_id ON public.sys_user_role (role_id);
COMMENT ON TABLE public.sys_user_role IS 'User to workspace sys_role mapping (app-enforced)';

CREATE TABLE IF NOT EXISTS refresh_tokens (
  id         UUID         NOT NULL,
  user_id    UUID         NOT NULL,
  jti        UUID         NOT NULL,
  expires_at TIMESTAMPTZ  NOT NULL,
  revoked_at TIMESTAMPTZ  NULL,
  created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_refresh_tokens_jti ON refresh_tokens (jti);
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens (user_id);

CREATE TABLE IF NOT EXISTS sys_tenant_user (
  id        UUID         NOT NULL,
  user_id   UUID         NOT NULL,
  tenant_id UUID         NOT NULL,
  role      tenant_role  NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_sys_tenant_user UNIQUE (user_id, tenant_id)
);
CREATE INDEX IF NOT EXISTS ix_sys_tenant_user_tenant_id ON sys_tenant_user (tenant_id);
CREATE INDEX IF NOT EXISTS ix_sys_tenant_user_user_id ON sys_tenant_user (user_id);

CREATE TABLE IF NOT EXISTS sys_workspaces (
  id        UUID         NOT NULL,
  tenant_id UUID         NOT NULL,
  name      VARCHAR(200) NOT NULL,
  slug      VARCHAR(64)  NOT NULL,
  status    BOOLEAN      NOT NULL DEFAULT true,
  remark    VARCHAR(500) NULL,
  create_at TIMESTAMPTZ  NULL DEFAULT now(),
  update_at TIMESTAMPTZ  NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_sys_workspaces_tenant_slug UNIQUE (tenant_id, slug)
);
CREATE INDEX IF NOT EXISTS ix_sys_workspaces_tenant_id ON sys_workspaces (tenant_id);
COMMENT ON COLUMN public.sys_workspaces.status IS 'true=正常 false=停用';
COMMENT ON COLUMN public.sys_workspaces.remark IS '备注';
COMMENT ON COLUMN public.sys_workspaces.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_workspaces.update_at IS '修改时间';

CREATE TABLE IF NOT EXISTS sys_workspace_user (
  id           UUID            NOT NULL,
  user_id      UUID            NOT NULL,
  workspace_id UUID            NOT NULL,
  role         workspace_role  NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_sys_workspace_user UNIQUE (user_id, workspace_id)
);
CREATE INDEX IF NOT EXISTS ix_sys_workspace_user_user_id ON sys_workspace_user (user_id);
CREATE INDEX IF NOT EXISTS ix_sys_workspace_user_workspace_id ON sys_workspace_user (workspace_id);


CREATE TABLE IF NOT EXISTS public.sys_ocr_tool (
  id UUID NOT NULL,
  workspace_id UUID NOT NULL,
  "name" VARCHAR(128) NOT NULL,
  url VARCHAR(128) NOT NULL,
  auth_type VARCHAR(64) NULL,
  user_name VARCHAR(64) NULL,
  user_passwd VARCHAR(128) NULL,
  api_key VARCHAR(1024) NULL,
  ocr_type varchar(16) NULL,
  ocr_config text NULL,
  remark VARCHAR(128) NULL,
  create_at TIMESTAMPTZ NULL DEFAULT now(),
  update_at TIMESTAMPTZ NULL,
  CONSTRAINT sys_ocr_tool_pk PRIMARY KEY (id)
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

CREATE TABLE IF NOT EXISTS public.agent_mcp_client (
  id UUID NOT NULL,
  workspace_id UUID NOT NULL,
  "name" VARCHAR(128) NOT NULL,
  transport VARCHAR(32) NOT NULL,
  config JSONB NOT NULL DEFAULT '{}'::jsonb,
  secrets JSONB NOT NULL DEFAULT '{}'::jsonb,
  enabled BOOLEAN NOT NULL DEFAULT true,
  remark VARCHAR(256) NULL,
  last_test_at TIMESTAMPTZ NULL,
  last_test_ok BOOLEAN NULL,
  create_at TIMESTAMPTZ NULL DEFAULT now(),
  update_at TIMESTAMPTZ NULL,
  CONSTRAINT agent_mcp_client_pk PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_agent_mcp_client_workspace_id ON agent_mcp_client (workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_mcp_client_workspace_name
  ON agent_mcp_client (workspace_id, "name");
COMMENT ON TABLE public.agent_mcp_client IS 'MCP 客户端连接配置（工作区隔离）';
COMMENT ON COLUMN public.agent_mcp_client.workspace_id IS '工作空间 id';
COMMENT ON COLUMN public.agent_mcp_client.transport IS 'STDIO | SSE | STREAMABLE_HTTP';
COMMENT ON COLUMN public.agent_mcp_client.config IS '非敏感连接配置 JSON';
COMMENT ON COLUMN public.agent_mcp_client.secrets IS '敏感配置 JSON（env/headers）';

CREATE TABLE IF NOT EXISTS public.agent_mcp_server (
  id UUID NOT NULL,
  workspace_id UUID NOT NULL,
  "name" VARCHAR(128) NOT NULL,
  slug VARCHAR(64) NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT true,
  exposure JSONB NOT NULL DEFAULT '{}'::jsonb,
  auth_type VARCHAR(32) NOT NULL DEFAULT 'NONE',
  auth_secret VARCHAR(512) NULL,
  remark VARCHAR(256) NULL,
  create_at TIMESTAMPTZ NULL DEFAULT now(),
  update_at TIMESTAMPTZ NULL,
  CONSTRAINT agent_mcp_server_pk PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_agent_mcp_server_workspace_id ON agent_mcp_server (workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_mcp_server_slug ON agent_mcp_server (slug);
COMMENT ON TABLE public.agent_mcp_server IS 'MCP 服务端暴露配置（工作区隔离）';
COMMENT ON COLUMN public.agent_mcp_server.slug IS '对外 URL 路径段，全局唯一';
COMMENT ON COLUMN public.agent_mcp_server.exposure IS '暴露范围 JSON（builtin_skills/mcp_client_ids）';

CREATE TABLE public.sys_dict (
     id uuid NOT NULL,
     dict_code varchar(64) NOT NULL,
     dict_name varchar(128) NULL,
     dict_sort int2 DEFAULT 0 NULL,
     create_at timestamptz NULL,
     update_at timestamptz NULL,
     CONSTRAINT sys_dict_pk PRIMARY KEY (id),
     CONSTRAINT uq_sys_dict_dict_code UNIQUE (dict_code)
);
COMMENT ON TABLE public.sys_dict IS '字典编码';

COMMENT ON COLUMN public.sys_dict.id IS 'uuid';
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
  CONSTRAINT uq_sys_dict_item_dict_code UNIQUE (dict_uuid, code)
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

CREATE TABLE IF NOT EXISTS public.sys_menu (
  id            UUID         NOT NULL,
  parent_id     UUID         NULL,
  menu_name     VARCHAR(64)  NOT NULL,
  i18n_key      VARCHAR(128) NULL,
  menu_key      VARCHAR(64)  NULL,
  order_num     INT          NOT NULL DEFAULT 0,
  path          VARCHAR(256) NULL,
  menu_type     CHAR(1)      NOT NULL,
  perms         VARCHAR(128) NULL,
  icon          VARCHAR(64)  NULL,
  visible       BOOLEAN      NOT NULL DEFAULT true,
  status        BOOLEAN      NOT NULL DEFAULT true,
  is_external   BOOLEAN      NOT NULL DEFAULT false,
  remark        VARCHAR(500) NULL,
  create_at     TIMESTAMPTZ  NULL DEFAULT now(),
  update_at     TIMESTAMPTZ  NULL,
  CONSTRAINT sys_menu_pk PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_sys_menu_parent_id ON public.sys_menu (parent_id);
CREATE INDEX IF NOT EXISTS ix_sys_menu_menu_type ON public.sys_menu (menu_type);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_menu_menu_key
  ON public.sys_menu (menu_key) WHERE menu_key IS NOT NULL;
COMMENT ON TABLE public.sys_menu IS '系统菜单（全局）';
COMMENT ON COLUMN public.sys_menu.parent_id IS '父菜单 id；NULL 为根';
COMMENT ON COLUMN public.sys_menu.menu_type IS 'M目录 C菜单 F按钮';

CREATE TABLE IF NOT EXISTS public.sys_role (
  id            UUID         NOT NULL,
  workspace_id  UUID         NOT NULL,
  role_name     VARCHAR(64)  NOT NULL,
  role_key      VARCHAR(64)  NOT NULL,
  role_sort     INT          NOT NULL DEFAULT 0,
  status        BOOLEAN      NOT NULL DEFAULT true,
  remark        VARCHAR(500) NULL,
  create_at     TIMESTAMPTZ  NULL DEFAULT now(),
  update_at     TIMESTAMPTZ  NULL,
  CONSTRAINT sys_role_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_role_workspace_role_key
  ON public.sys_role (workspace_id, role_key);
CREATE INDEX IF NOT EXISTS ix_sys_role_workspace_id ON public.sys_role (workspace_id);
CREATE INDEX IF NOT EXISTS ix_sys_role_role_sort ON public.sys_role (role_sort);
COMMENT ON TABLE public.sys_role IS '工作空间角色';
COMMENT ON COLUMN public.sys_role.workspace_id IS '所属 workspace';
COMMENT ON COLUMN public.sys_role.role_key IS '权限字符；workspace 内唯一';

CREATE TABLE IF NOT EXISTS public.sys_role_menu (
  id       UUID NOT NULL,
  role_id  UUID NOT NULL,
  menu_id  UUID NOT NULL,
  CONSTRAINT sys_role_menu_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_role_menu_role_menu
  ON public.sys_role_menu (role_id, menu_id);
CREATE INDEX IF NOT EXISTS ix_sys_role_menu_role_id ON public.sys_role_menu (role_id);
CREATE INDEX IF NOT EXISTS ix_sys_role_menu_menu_id ON public.sys_role_menu (menu_id);
COMMENT ON TABLE public.sys_role_menu IS '角色菜单权限关联';

CREATE TABLE public.sys_models (
	id uuid NOT NULL,
	workspace_id uuid NOT NULL,
	provider_name varchar(128) NOT NULL,
	model_name varchar(128) NOT NULL,
	enabled bool DEFAULT true NOT NULL,
	auth_type varchar(64) NOT NULL,
	endpoint_url varchar(128) NULL,
	api_key varchar(128) NULL,
	auth_name varchar(64) NULL,
	auth_passwd varchar(128) NULL,
	context_size int2 NULL,
	max_tokens int2 NULL,
	model_config text NULL,
	tags jsonb DEFAULT '["TEXT"]'::jsonb NOT NULL,
	create_at timestamptz NULL,
	update_at timestamptz NULL,
	CONSTRAINT sys_models_pk PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_sys_models_workspace_id ON public.sys_models (workspace_id);
COMMENT ON TABLE public.sys_models IS '模型配置';

COMMENT ON COLUMN public.sys_models.id IS 'id';
COMMENT ON COLUMN public.sys_models.workspace_id IS '工作空间id';
COMMENT ON COLUMN public.sys_models.provider_name IS '模型供应商id';
COMMENT ON COLUMN public.sys_models.model_name IS '模型名称';
COMMENT ON COLUMN public.sys_models.enabled IS '状态';
COMMENT ON COLUMN public.sys_models.auth_type IS '认证方式';
COMMENT ON COLUMN public.sys_models.endpoint_url IS '模型地址';
COMMENT ON COLUMN public.sys_models.api_key IS 'api key';
COMMENT ON COLUMN public.sys_models.auth_name IS '账号';
COMMENT ON COLUMN public.sys_models.auth_passwd IS '密码';
COMMENT ON COLUMN public.sys_models.context_size IS '上下文窗口大小';
COMMENT ON COLUMN public.sys_models.max_tokens IS '最大 token 上限';
COMMENT ON COLUMN public.sys_models.model_config IS '其它配置项';
COMMENT ON COLUMN public.sys_models.tags IS '模型用途标签（MODEL_TAG 字典 code 数组）';
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
	bucket_name varchar(63) NULL,
	local_path varchar(128) NULL,
	"type" varchar(16) NULL,
	enabled bool DEFAULT true NOT NULL,
	auth_type varchar(64) NOT NULL,
	endpoint_url varchar(128) NULL,
	api_key varchar(128) NULL,
	secret_key varchar(128) NULL,
	auth_name varchar(64) NULL,
	auth_passwd varchar(128) NULL,
	create_at timestamptz NULL,
	update_at timestamptz NULL,
	CONSTRAINT sys_store_pk PRIMARY KEY (id)
);

COMMENT ON TABLE public.sys_storage IS '文件存储';
COMMENT ON COLUMN public.sys_storage.id IS 'id';
COMMENT ON COLUMN public.sys_storage.workspace_id IS '工作空间id';
COMMENT ON COLUMN public.sys_storage."name" IS '配置显示名称';
COMMENT ON COLUMN public.sys_storage.bucket_name IS 'S3 桶名（对象接口使用）';
COMMENT ON COLUMN public.sys_storage.local_path IS 'LOCAL 类型相对 workspace 根的路径段';
COMMENT ON COLUMN public.sys_storage."type" IS '存储类型';
COMMENT ON COLUMN public.sys_storage.enabled IS '状态';
COMMENT ON COLUMN public.sys_storage.auth_type IS '认证方式';
COMMENT ON COLUMN public.sys_storage.endpoint_url IS '地址';
COMMENT ON COLUMN public.sys_storage.api_key IS 'api key';
COMMENT ON COLUMN public.sys_storage.secret_key IS 'secret key (API_KEY 认证时与 api_key 配对)';
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
  ADD COLUMN IF NOT EXISTS last_status varchar(16),
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
  ALTER COLUMN timezone DROP NOT NULL,
  ALTER COLUMN enabled SET DEFAULT true,
  ALTER COLUMN last_status TYPE varchar(16),
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

CREATE TABLE public.ocr_file_paddleocr (
   id uuid NOT NULL, -- id
   workspace_id uuid NOT NULL, -- 工作空间id
   file_id uuid NOT NULL, -- ocr_file.id
   page_index int2 NULL, -- 页面序号
   markdown_text text NULL, -- markdown文本
   markdown_images text NULL, -- markdown图片
   page_width int4 NULL, -- 页宽（像素）
   page_height int4 NULL, -- 页高（像素）
   layout_blocks_json jsonb NULL, -- LayoutBlock[] 真源
   page_raster_object_key varchar(1024) NULL, -- 页图 S3 object_key
   layout_version int2 NULL DEFAULT 1, -- LDM schema 版本
   create_at timestamptz NULL, -- 创建日期
   update_at timestamptz NULL, -- 更新日期
   CONSTRAINT ocr_file_paddleocr_pk PRIMARY KEY (id)
);
COMMENT ON TABLE public.ocr_file_paddleocr IS 'PaddleOCR结果';
COMMENT ON COLUMN public.ocr_file_paddleocr.id IS 'id';
COMMENT ON COLUMN public.ocr_file_paddleocr.workspace_id IS '工作空间id';
COMMENT ON COLUMN public.ocr_file_paddleocr.file_id IS 'ocr_file.id';
COMMENT ON COLUMN public.ocr_file_paddleocr.page_index IS '页面序号';
COMMENT ON COLUMN public.ocr_file_paddleocr.markdown_text IS 'markdown文本';
COMMENT ON COLUMN public.ocr_file_paddleocr.markdown_images IS 'markdown图片';
COMMENT ON COLUMN public.ocr_file_paddleocr.page_width IS '页宽（像素）';
COMMENT ON COLUMN public.ocr_file_paddleocr.page_height IS '页高（像素）';
COMMENT ON COLUMN public.ocr_file_paddleocr.layout_blocks_json IS 'LayoutBlock[] 真源';
COMMENT ON COLUMN public.ocr_file_paddleocr.page_raster_object_key IS '页图 S3 object_key';
COMMENT ON COLUMN public.ocr_file_paddleocr.layout_version IS 'LDM schema 版本';
COMMENT ON COLUMN public.ocr_file_paddleocr.create_at IS '创建日期';
COMMENT ON COLUMN public.ocr_file_paddleocr.update_at IS '更新日期';

CREATE TABLE public.ocr_file_mineru (
    id uuid NOT NULL, -- id
    workspace_id uuid NOT NULL, -- 工作空间id
    file_id uuid NOT NULL, -- ocr_file.id
    markdown_text text NULL, -- markdown文本
    markdown_images text NULL, -- markdown图片
    page_index int2 NULL, -- 页面序号
    page_width int4 NULL, -- 页宽（像素）
    page_height int4 NULL, -- 页高（像素）
    layout_blocks_json jsonb NULL, -- LayoutBlock[] 真源
    page_raster_object_key varchar(1024) NULL, -- 页图 S3 object_key
    layout_version int2 NULL DEFAULT 1, -- LDM schema 版本
    create_at timestamptz NULL, -- 创建日期
    update_at timestamptz NULL, -- 更新日期
    CONSTRAINT ocr_file_mineru_pk PRIMARY KEY (id)
);
CREATE INDEX ocr_file_mineru_file_id_idx ON public.ocr_file_mineru USING btree (file_id);
CREATE INDEX ocr_file_mineru_workspace_id_idx ON public.ocr_file_mineru USING btree (workspace_id);
COMMENT ON TABLE public.ocr_file_mineru IS 'mineru结果';
COMMENT ON COLUMN public.ocr_file_mineru.id IS 'id';
COMMENT ON COLUMN public.ocr_file_mineru.workspace_id IS '工作空间id';
COMMENT ON COLUMN public.ocr_file_mineru.file_id IS 'ocr_file.id';
COMMENT ON COLUMN public.ocr_file_mineru.markdown_text IS 'markdown文本';
COMMENT ON COLUMN public.ocr_file_mineru.markdown_images IS 'markdown图片';
COMMENT ON COLUMN public.ocr_file_mineru.page_index IS '页面序号';
COMMENT ON COLUMN public.ocr_file_mineru.page_width IS '页宽（像素）';
COMMENT ON COLUMN public.ocr_file_mineru.page_height IS '页高（像素）';
COMMENT ON COLUMN public.ocr_file_mineru.layout_blocks_json IS 'LayoutBlock[] 真源';
COMMENT ON COLUMN public.ocr_file_mineru.page_raster_object_key IS '页图 S3 object_key';
COMMENT ON COLUMN public.ocr_file_mineru.layout_version IS 'LDM schema 版本';
COMMENT ON COLUMN public.ocr_file_mineru.create_at IS '创建日期';
COMMENT ON COLUMN public.ocr_file_mineru.update_at IS '更新日期';

CREATE TABLE public.ocr_file_log (
     id uuid NOT NULL, -- id
     workspace_id uuid NOT NULL, -- 工作空间id
     ocr_file_id uuid NOT NULL, -- ocr_file.id
     status varchar NULL, -- 状态(Y-成功，N-失败，P-运行中)
     remark text NULL, -- 备注，记录错误日志信息
     create_at timestamptz NULL, -- 创建时间
     update_at timestamptz NULL, -- 更新时间
     CONSTRAINT ocr_file_log_pk PRIMARY KEY (id)
);
CREATE INDEX ocr_file_log_ocr_file_id_idx ON public.ocr_file_log USING btree (ocr_file_id);
CREATE INDEX ocr_file_log_workspace_id_idx ON public.ocr_file_log USING btree (workspace_id);
COMMENT ON TABLE public.ocr_file_log IS 'OCR执行日志';
COMMENT ON COLUMN public.ocr_file_log.id IS 'id';
COMMENT ON COLUMN public.ocr_file_log.workspace_id IS '工作空间id';
COMMENT ON COLUMN public.ocr_file_log.ocr_file_id IS 'ocr_file.id';
COMMENT ON COLUMN public.ocr_file_log.status IS '状态(Y-成功，N-失败，P-运行中)';
COMMENT ON COLUMN public.ocr_file_log.remark IS '备注，记录错误日志信息';
COMMENT ON COLUMN public.ocr_file_log.create_at IS '创建时间';
COMMENT ON COLUMN public.ocr_file_log.update_at IS '更新时间';

-- ---------------------------------------------------------------------------
-- Agent（智能体）：会话、单次 run、消息历史、细粒度运行节点（与 ORM 一致）
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.agent_session (
  id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  created_by uuid NULL,
  title varchar(200) NULL,
  agent_key varchar(64) NULL,
  status varchar(16) NOT NULL DEFAULT 'active',
  meta_json jsonb NULL,
  usage_json jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NULL,
  summary_text text NULL,
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_agent_session_workspace_id ON public.agent_session (workspace_id);
CREATE INDEX IF NOT EXISTS ix_agent_session_workspace_updated ON public.agent_session (workspace_id, updated_at);
CREATE INDEX IF NOT EXISTS ix_agent_session_created_by ON public.agent_session (created_by);
COMMENT ON TABLE public.agent_session IS '智能体会话容器';
COMMENT ON COLUMN public.agent_session.id IS '会话主键';
COMMENT ON COLUMN public.agent_session.workspace_id IS '工作空间 id';
COMMENT ON COLUMN public.agent_session.created_by IS '创建人（用户 id）';
COMMENT ON COLUMN public.agent_session.title IS '展示标题';
COMMENT ON COLUMN public.agent_session.agent_key IS '智能体配置/技能组合键';
COMMENT ON COLUMN public.agent_session.status IS '会话状态，如 active / archived';
COMMENT ON COLUMN public.agent_session.meta_json IS '扩展元数据(JSONB)';
COMMENT ON COLUMN public.agent_session.usage_json IS '会话累计 token 用量(JSONB，含 by_phase)';
COMMENT ON COLUMN public.agent_session.created_at IS '创建时间';
COMMENT ON COLUMN public.agent_session.updated_at IS '更新时间';

CREATE TABLE IF NOT EXISTS public.agent_run (
  id uuid NOT NULL,
  session_id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  triggered_by uuid NULL,
  status varchar(16) NOT NULL DEFAULT 'running',
  started_at timestamptz NOT NULL,
  finished_at timestamptz NULL,
  model varchar(128) NOT NULL,
  provider_kind varchar(32) NULL,
  error_code varchar(64) NULL,
  error_message text NULL,
  usage_json jsonb NULL,
  request_meta_json jsonb NULL,
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_agent_run_session_id ON public.agent_run (session_id);
CREATE INDEX IF NOT EXISTS ix_agent_run_workspace_id ON public.agent_run (workspace_id);
CREATE INDEX IF NOT EXISTS ix_agent_run_triggered_by ON public.agent_run (triggered_by);
CREATE INDEX IF NOT EXISTS ix_agent_run_session_started ON public.agent_run (session_id, started_at);
COMMENT ON TABLE public.agent_run IS '单次智能体运行（与 SSE run_id 一致）';
COMMENT ON COLUMN public.agent_run.id IS 'run 主键，即对外 run_id';
COMMENT ON COLUMN public.agent_run.session_id IS '所属会话';
COMMENT ON COLUMN public.agent_run.workspace_id IS '冗余工作空间，便于鉴权与查询';
COMMENT ON COLUMN public.agent_run.triggered_by IS '触发用户';
COMMENT ON COLUMN public.agent_run.status IS 'running / success / failed / cancelled';
COMMENT ON COLUMN public.agent_run.started_at IS '开始时间';
COMMENT ON COLUMN public.agent_run.finished_at IS '结束时间';
COMMENT ON COLUMN public.agent_run.model IS '本次调用模型快照';
COMMENT ON COLUMN public.agent_run.provider_kind IS '上游策略类型快照';
COMMENT ON COLUMN public.agent_run.error_code IS '失败时业务错误码';
COMMENT ON COLUMN public.agent_run.error_message IS '失败时说明';
COMMENT ON COLUMN public.agent_run.usage_json IS 'token 等用量(JSONB)';
COMMENT ON COLUMN public.agent_run.request_meta_json IS '请求侧非密钥元数据(JSONB)';

CREATE TABLE IF NOT EXISTS public.agent_message (
  id uuid NOT NULL,
  session_id uuid NOT NULL,
  seq int NOT NULL,
  role varchar(16) NOT NULL,
  content text NULL,
  reasoning_text text NULL,
  tool_calls_json jsonb NULL,
  tool_call_id varchar(64) NULL,
  tool_name varchar(128) NULL,
  meta_json jsonb NULL,
  run_id uuid NULL,
  message_json jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id),
  CONSTRAINT uq_agent_message_session_seq UNIQUE (session_id, seq)
);
CREATE INDEX IF NOT EXISTS ix_agent_message_session_id ON public.agent_message (session_id);
CREATE INDEX IF NOT EXISTS ix_agent_message_session_seq ON public.agent_message (session_id, seq);
CREATE INDEX IF NOT EXISTS ix_agent_message_run_id ON public.agent_message (run_id);
COMMENT ON TABLE public.agent_message IS '会话消息（OpenAI 角色含 tool/tool_calls）';
COMMENT ON COLUMN public.agent_message.id IS '消息主键';
COMMENT ON COLUMN public.agent_message.session_id IS '所属会话';
COMMENT ON COLUMN public.agent_message.seq IS '会话内顺序号';
COMMENT ON COLUMN public.agent_message.role IS 'system / user / assistant / tool';
COMMENT ON COLUMN public.agent_message.content IS '文本内容';
COMMENT ON COLUMN public.agent_message.reasoning_text IS '助手消息对应的思考合并纯文本';
COMMENT ON COLUMN public.agent_message.tool_calls_json IS 'assistant 的 tool_calls(JSONB)';
COMMENT ON COLUMN public.agent_message.tool_call_id IS 'tool 消息关联的调用 id';
COMMENT ON COLUMN public.agent_message.tool_name IS '工具名冗余';
COMMENT ON COLUMN public.agent_message.meta_json IS '扩展(JSONB)';
COMMENT ON COLUMN public.agent_message.run_id IS '产生该条的 run（可空）';
COMMENT ON COLUMN public.agent_message.created_at IS '创建时间';
COMMENT ON COLUMN public.agent_message.message_json IS 'LangChain 消息序列化(JSONB)';

CREATE TABLE IF NOT EXISTS public.agent_message_attachment (
  id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  session_id uuid NOT NULL,
  message_id uuid NOT NULL,
  object_key varchar(1024) NOT NULL,
  storage_kind varchar(16) NOT NULL,
  file_name varchar(256) NULL,
  content_type varchar(128) NULL,
  size bigint NULL,
  kind varchar(16) NOT NULL,
  created_by uuid NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT agent_message_attachment_pk PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_agent_message_attachment_workspace_id ON public.agent_message_attachment (workspace_id);
CREATE INDEX IF NOT EXISTS ix_agent_message_attachment_session_id ON public.agent_message_attachment (session_id);
CREATE INDEX IF NOT EXISTS ix_agent_message_attachment_message_id ON public.agent_message_attachment (message_id);
COMMENT ON TABLE public.agent_message_attachment IS 'Agent 对话消息附件元数据（不含 download_url）';
COMMENT ON COLUMN public.agent_message_attachment.storage_kind IS '上传时快照: S3 / LOCAL / DEFAULT_LOCAL';
COMMENT ON COLUMN public.agent_message_attachment.kind IS 'image | file';

CREATE TABLE IF NOT EXISTS public.agent_plan (
  id uuid NOT NULL,
  run_id uuid NOT NULL,
  steps_json jsonb NOT NULL,
  status varchar(16) NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_agent_plan_run_id ON public.agent_plan (run_id);
COMMENT ON TABLE public.agent_plan IS '单次 run 的结构化计划';

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
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_agent_ltm_workspace_id ON public.agent_long_term_memory (workspace_id);
CREATE INDEX IF NOT EXISTS ix_agent_ltm_session_id ON public.agent_long_term_memory (session_id);
CREATE INDEX IF NOT EXISTS ix_agent_ltm_workspace_session ON public.agent_long_term_memory (workspace_id, session_id);
COMMENT ON TABLE public.agent_long_term_memory IS '长期记忆（SQL 检索）';

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

CREATE TABLE IF NOT EXISTS public.agent_run_node (
  id uuid NOT NULL,
  run_id uuid NOT NULL,
  parent_node_id uuid NULL,
  sequence_idx int NOT NULL,
  node_type varchar(32) NOT NULL,
  node_name varchar(128) NOT NULL,
  status varchar(16) NOT NULL DEFAULT 'pending',
  inputs_json jsonb NULL,
  outputs_json jsonb NULL,
  error_code varchar(64) NULL,
  error_message text NULL,
  reasoning_text text NULL,
  started_at timestamptz NULL,
  finished_at timestamptz NULL,
  meta_json jsonb NULL,
  usage_json jsonb NULL,
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_agent_run_node_run_id ON public.agent_run_node (run_id);
CREATE INDEX IF NOT EXISTS ix_agent_run_node_parent_node_id ON public.agent_run_node (parent_node_id);
CREATE INDEX IF NOT EXISTS ix_agent_run_node_run_parent_seq ON public.agent_run_node (run_id, parent_node_id, sequence_idx);
COMMENT ON TABLE public.agent_run_node IS '单次 run 的细粒度节点树';
COMMENT ON COLUMN public.agent_run_node.id IS '节点主键';
COMMENT ON COLUMN public.agent_run_node.run_id IS '所属 run';
COMMENT ON COLUMN public.agent_run_node.parent_node_id IS '父节点（树形）';
COMMENT ON COLUMN public.agent_run_node.sequence_idx IS '同级排序序号';
COMMENT ON COLUMN public.agent_run_node.node_type IS '节点类型，如 llm.round / tool.execute';
COMMENT ON COLUMN public.agent_run_node.node_name IS '展示名称';
COMMENT ON COLUMN public.agent_run_node.status IS 'pending / running / success / failed / skipped';
COMMENT ON COLUMN public.agent_run_node.inputs_json IS '输入快照(JSONB)';
COMMENT ON COLUMN public.agent_run_node.outputs_json IS '输出快照(JSONB)';
COMMENT ON COLUMN public.agent_run_node.error_code IS '错误码';
COMMENT ON COLUMN public.agent_run_node.error_message IS '错误说明';
COMMENT ON COLUMN public.agent_run_node.reasoning_text IS '该 llm.round 节点 LLM 调用的思考全文';
COMMENT ON COLUMN public.agent_run_node.started_at IS '开始时间';
COMMENT ON COLUMN public.agent_run_node.finished_at IS '结束时间';
COMMENT ON COLUMN public.agent_run_node.meta_json IS '扩展(JSONB)';
COMMENT ON COLUMN public.agent_run_node.usage_json IS '该节点 LLM token 用量(JSONB，OpenAI 兼容 + 按需 details)';

-- ---------------------------------------------------------------------------
-- LangGraph checkpoint（AsyncPostgresSaver；列定义对齐 langgraph-checkpoint-postgres 3.x）
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.checkpoints (
  thread_id text NOT NULL,
  checkpoint_ns text NOT NULL DEFAULT '',
  checkpoint_id text NOT NULL,
  parent_checkpoint_id text NULL,
  type text NULL,
  checkpoint jsonb NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}',
  create_at timestamptz NOT NULL DEFAULT now(),
  update_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);
CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx ON public.checkpoints (thread_id);
CREATE INDEX IF NOT EXISTS ix_checkpoints_create_at ON public.checkpoints (create_at);
COMMENT ON TABLE public.checkpoints IS 'LangGraph checkpoint 主表';
COMMENT ON COLUMN public.checkpoints.create_at IS '行创建时间（清理依据）';
COMMENT ON COLUMN public.checkpoints.update_at IS '行最后更新时间';

CREATE TABLE IF NOT EXISTS public.checkpoint_blobs (
  thread_id text NOT NULL,
  checkpoint_ns text NOT NULL DEFAULT '',
  channel text NOT NULL,
  version text NOT NULL,
  type text NOT NULL,
  blob bytea NULL,
  create_at timestamptz NOT NULL DEFAULT now(),
  update_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);
CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_id_idx ON public.checkpoint_blobs (thread_id);
CREATE INDEX IF NOT EXISTS ix_checkpoint_blobs_create_at ON public.checkpoint_blobs (create_at);
COMMENT ON TABLE public.checkpoint_blobs IS 'LangGraph checkpoint blob 分片';
COMMENT ON COLUMN public.checkpoint_blobs.create_at IS '行创建时间（清理依据）';
COMMENT ON COLUMN public.checkpoint_blobs.update_at IS '行最后更新时间';

CREATE TABLE IF NOT EXISTS public.checkpoint_writes (
  thread_id text NOT NULL,
  checkpoint_ns text NOT NULL DEFAULT '',
  checkpoint_id text NOT NULL,
  task_id text NOT NULL,
  task_path text NOT NULL DEFAULT '',
  idx integer NOT NULL,
  channel text NOT NULL,
  type text NULL,
  blob bytea NOT NULL,
  create_at timestamptz NOT NULL DEFAULT now(),
  update_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);
CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_id_idx ON public.checkpoint_writes (thread_id);
CREATE INDEX IF NOT EXISTS ix_checkpoint_writes_create_at ON public.checkpoint_writes (create_at);
COMMENT ON TABLE public.checkpoint_writes IS 'LangGraph checkpoint 写入缓冲';
COMMENT ON COLUMN public.checkpoint_writes.create_at IS '行创建时间（清理依据）';
COMMENT ON COLUMN public.checkpoint_writes.update_at IS '行最后更新时间';

-- ---------------------------------------------------------------------------
-- Document translation（文档翻译）：任务与段落（与 ORM 一致，无库级外键）
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.doc_translate_job (
  id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  created_by uuid NULL,
  title varchar(256) NULL,
  file_name varchar(256) NULL,
  file_ext varchar(16) NOT NULL,
  source_lang varchar(32) NOT NULL,
  target_lang varchar(32) NOT NULL,
  model_id uuid NOT NULL,
  status varchar(32) NOT NULL,
  source_object_key varchar(1024) NOT NULL,
  result_object_key varchar(1024) NULL,
  ocr_file_id uuid NULL,
  progress smallint NOT NULL DEFAULT 0,
  segment_total integer NOT NULL DEFAULT 0,
  segment_done integer NOT NULL DEFAULT 0,
  error_code varchar(64) NULL,
  error_message text NULL,
  layout_snapshot_json jsonb NULL,
  layout_source varchar(32) NULL,
  create_at timestamptz NULL DEFAULT now(),
  update_at timestamptz NULL,
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_doc_translate_job_workspace_id ON public.doc_translate_job (workspace_id);
CREATE INDEX IF NOT EXISTS ix_doc_translate_job_workspace_updated ON public.doc_translate_job (workspace_id, updated_at);
CREATE INDEX IF NOT EXISTS ix_doc_translate_job_created_by ON public.doc_translate_job (created_by);
CREATE INDEX IF NOT EXISTS ix_doc_translate_job_model_id ON public.doc_translate_job (model_id);
CREATE INDEX IF NOT EXISTS ix_doc_translate_job_ocr_file_id ON public.doc_translate_job (ocr_file_id);
COMMENT ON TABLE public.doc_translate_job IS '文档翻译任务（一条侧栏历史）';
COMMENT ON COLUMN public.doc_translate_job.id IS '任务主键';
COMMENT ON COLUMN public.doc_translate_job.workspace_id IS '工作空间 id';
COMMENT ON COLUMN public.doc_translate_job.created_by IS '发起人用户 id（逻辑关联，无 FK）';
COMMENT ON COLUMN public.doc_translate_job.title IS '侧栏展示标题';
COMMENT ON COLUMN public.doc_translate_job.file_name IS '原始文件名';
COMMENT ON COLUMN public.doc_translate_job.file_ext IS '规范化小写后缀';
COMMENT ON COLUMN public.doc_translate_job.source_lang IS '源语言字典 code';
COMMENT ON COLUMN public.doc_translate_job.target_lang IS '目标语言字典 code';
COMMENT ON COLUMN public.doc_translate_job.model_id IS 'sys_models.id（逻辑关联，无 FK）';
COMMENT ON COLUMN public.doc_translate_job.status IS 'PENDING/OCR_RUNNING/EXTRACTING/TRANSLATING/ASSEMBLING/SUCCESS/FAILED';
COMMENT ON COLUMN public.doc_translate_job.source_object_key IS 'S3 源文件 object_key';
COMMENT ON COLUMN public.doc_translate_job.result_object_key IS 'S3 译文 object_key';
COMMENT ON COLUMN public.doc_translate_job.ocr_file_id IS '扫描 PDF 时关联 ocr_file.id（逻辑关联，无 FK）';
COMMENT ON COLUMN public.doc_translate_job.progress IS '进度 0-100';
COMMENT ON COLUMN public.doc_translate_job.segment_total IS '总段落数';
COMMENT ON COLUMN public.doc_translate_job.segment_done IS '已完成段落数';
COMMENT ON COLUMN public.doc_translate_job.error_code IS '失败错误码';
COMMENT ON COLUMN public.doc_translate_job.error_message IS '失败详情';
COMMENT ON COLUMN public.doc_translate_job.layout_snapshot_json IS '抽取完成后的 LDM 快照';
COMMENT ON COLUMN public.doc_translate_job.layout_source IS 'native / ocr / hybrid';
COMMENT ON COLUMN public.doc_translate_job.create_at IS '创建时间';
COMMENT ON COLUMN public.doc_translate_job.update_at IS '更新时间';

CREATE TABLE IF NOT EXISTS public.doc_translate_segment (
  id uuid NOT NULL,
  job_id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  seq integer NOT NULL,
  source_text text NOT NULL,
  translated_text text NULL,
  status varchar(16) NOT NULL,
  anchor_json jsonb NULL,
  error_message text NULL,
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_doc_translate_segment_job_id ON public.doc_translate_segment (job_id);
CREATE INDEX IF NOT EXISTS ix_doc_translate_segment_workspace_id ON public.doc_translate_segment (workspace_id);
CREATE INDEX IF NOT EXISTS ix_doc_translate_segment_job_seq ON public.doc_translate_segment (job_id, seq);
COMMENT ON TABLE public.doc_translate_segment IS '文档翻译段落（左右对照数据源）';
COMMENT ON COLUMN public.doc_translate_segment.id IS '段落主键';
COMMENT ON COLUMN public.doc_translate_segment.job_id IS '所属 doc_translate_job.id（逻辑关联，无 FK）';
COMMENT ON COLUMN public.doc_translate_segment.workspace_id IS '工作空间 id';
COMMENT ON COLUMN public.doc_translate_segment.seq IS '段落序号（从 0 起）';
COMMENT ON COLUMN public.doc_translate_segment.source_text IS '原文段落';
COMMENT ON COLUMN public.doc_translate_segment.translated_text IS '译文段落';
COMMENT ON COLUMN public.doc_translate_segment.status IS 'PENDING/DONE/FAILED';
COMMENT ON COLUMN public.doc_translate_segment.anchor_json IS '策略写回锚点 JSON';
COMMENT ON COLUMN public.doc_translate_segment.error_message IS '单段失败信息';

-- dataset knowledge base tables (no FOREIGN KEY; app-layer cascade)

CREATE TABLE IF NOT EXISTS public.dataset (
  id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  name varchar(255) NOT NULL,
  description text NULL,
  provider varchar(255) NOT NULL DEFAULT 'vendor',
  permission varchar(255) NOT NULL DEFAULT 'only_me',
  data_source_type varchar(255) NULL,
  indexing_technique varchar(255) NULL,
  index_struct text NULL,
  embedding_model varchar(255) NULL,
  embedding_model_provider varchar(255) NULL,
  keyword_number integer NULL DEFAULT 10,
  collection_binding_id uuid NULL,
  retrieval_model jsonb NULL,
  chunk_structure varchar(255) NULL,
  created_by uuid NOT NULL,
  updated_by uuid NULL,
  create_at timestamptz NULL DEFAULT now(),
  update_at timestamptz NULL,
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_dataset_workspace_id ON public.dataset (workspace_id);

CREATE TABLE IF NOT EXISTS public.dataset_process_rule (
  id uuid NOT NULL,
  dataset_id uuid NOT NULL,
  mode varchar(255) NOT NULL DEFAULT 'automatic',
  rules text NULL,
  created_by uuid NOT NULL,
  create_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_dataset_process_rule_dataset_id ON public.dataset_process_rule (dataset_id);

CREATE TABLE IF NOT EXISTS public.dataset_upload_file (
  id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  storage_key varchar(512) NOT NULL,
  name varchar(255) NOT NULL,
  size integer NOT NULL,
  extension varchar(32) NOT NULL,
  mime_type varchar(128) NULL,
  created_by uuid NOT NULL,
  create_at timestamptz NULL DEFAULT now(),
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_dataset_upload_file_workspace_id ON public.dataset_upload_file (workspace_id);

CREATE TABLE IF NOT EXISTS public.dataset_document (
  id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  dataset_id uuid NOT NULL,
  position integer NOT NULL,
  data_source_type varchar(255) NOT NULL,
  data_source_info text NULL,
  dataset_process_rule_id uuid NULL,
  batch varchar(255) NOT NULL,
  name varchar(255) NOT NULL,
  created_from varchar(255) NOT NULL,
  created_by uuid NOT NULL,
  file_id text NULL,
  word_count integer NULL,
  indexing_status varchar(255) NOT NULL DEFAULT 'waiting',
  enabled boolean NOT NULL DEFAULT true,
  archived boolean NOT NULL DEFAULT false,
  is_paused boolean NULL DEFAULT false,
  doc_form varchar(255) NOT NULL DEFAULT 'text_model',
  doc_type varchar(40) NULL,
  doc_language varchar(255) NULL,
  error text NULL,
  tokens integer NULL,
  indexing_latency double precision NULL,
  processing_started_at timestamptz NULL,
  parsing_completed_at timestamptz NULL,
  cleaning_completed_at timestamptz NULL,
  splitting_completed_at timestamptz NULL,
  completed_at timestamptz NULL,
  stopped_at timestamptz NULL,
  create_at timestamptz NOT NULL DEFAULT now(),
  update_at timestamptz NULL,
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_dataset_document_dataset_id ON public.dataset_document (dataset_id);
CREATE INDEX IF NOT EXISTS ix_dataset_document_workspace_id ON public.dataset_document (workspace_id);

CREATE TABLE IF NOT EXISTS public.dataset_document_segment (
  id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  dataset_id uuid NOT NULL,
  document_id uuid NOT NULL,
  position integer NOT NULL,
  content text NOT NULL,
  answer text NULL,
  word_count integer NOT NULL,
  tokens integer NOT NULL,
  keywords jsonb NULL,
  index_node_id varchar(255) NULL,
  index_node_hash varchar(255) NULL,
  hit_count integer NOT NULL DEFAULT 0,
  enabled boolean NOT NULL DEFAULT true,
  status varchar(255) NOT NULL DEFAULT 'waiting',
  error text NULL,
  created_by uuid NOT NULL,
  create_at timestamptz NOT NULL DEFAULT now(),
  update_at timestamptz NULL,
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_dataset_document_segment_dataset_id ON public.dataset_document_segment (dataset_id);
CREATE INDEX IF NOT EXISTS ix_dataset_document_segment_document_id ON public.dataset_document_segment (document_id);

CREATE TABLE IF NOT EXISTS public.dataset_child_chunk (
  id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  dataset_id uuid NOT NULL,
  document_id uuid NOT NULL,
  segment_id uuid NOT NULL,
  position integer NOT NULL,
  content text NOT NULL,
  word_count integer NOT NULL,
  index_node_id varchar(255) NULL,
  index_node_hash varchar(255) NULL,
  type varchar(255) NOT NULL DEFAULT 'automatic',
  created_by uuid NOT NULL,
  create_at timestamptz NOT NULL DEFAULT now(),
  update_at timestamptz NULL,
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_dataset_child_chunk_segment_id ON public.dataset_child_chunk (segment_id);

CREATE TABLE IF NOT EXISTS public.dataset_keyword_table (
  id uuid NOT NULL,
  dataset_id uuid NOT NULL,
  keyword_table text NOT NULL,
  data_source_type varchar(255) NOT NULL DEFAULT 'database',
  PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_dataset_keyword_table_dataset_id ON public.dataset_keyword_table (dataset_id);

CREATE TABLE IF NOT EXISTS public.dataset_embedding (
  id uuid NOT NULL,
  model_name varchar(255) NOT NULL DEFAULT 'text-embedding-ada-002',
  hash varchar(64) NOT NULL,
  embedding bytea NOT NULL,
  provider_name varchar(255) NOT NULL DEFAULT '',
  create_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id),
  CONSTRAINT dataset_embedding_hash_idx UNIQUE (model_name, hash, provider_name)
);

CREATE TABLE IF NOT EXISTS public.dataset_collection_binding (
  id uuid NOT NULL,
  provider_name varchar(255) NOT NULL,
  model_name varchar(255) NOT NULL,
  type varchar(40) NOT NULL DEFAULT 'dataset',
  collection_name varchar(64) NOT NULL,
  create_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_dataset_collection_binding_provider_model ON public.dataset_collection_binding (provider_name, model_name);

CREATE TABLE IF NOT EXISTS public.dataset_query (
  id uuid NOT NULL,
  dataset_id uuid NOT NULL,
  content text NOT NULL,
  source varchar(255) NOT NULL,
  source_app_id uuid NULL,
  created_by_role varchar(255) NOT NULL,
  created_by uuid NOT NULL,
  create_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_dataset_query_dataset_id ON public.dataset_query (dataset_id);
