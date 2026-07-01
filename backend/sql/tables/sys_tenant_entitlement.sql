-- Super-admin grants feature modules to tenants (ABAC)
CREATE TABLE IF NOT EXISTS public.sys_tenant_entitlement (
  id                 UUID         NOT NULL,
  tenant_id          UUID         NOT NULL,
  feature_code       VARCHAR(64)  NOT NULL,
  enabled            BOOLEAN      NOT NULL DEFAULT true,
  granted_by_user_id UUID         NOT NULL,
  create_at          TIMESTAMPTZ  NULL DEFAULT now(),
  update_at          TIMESTAMPTZ  NULL,
  CONSTRAINT sys_tenant_entitlement_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_tenant_entitlement_tenant_feature
  ON public.sys_tenant_entitlement (tenant_id, feature_code);
CREATE INDEX IF NOT EXISTS ix_sys_tenant_entitlement_tenant_id
  ON public.sys_tenant_entitlement (tenant_id);

COMMENT ON TABLE public.sys_tenant_entitlement IS '租户功能开通（超管授权）';
COMMENT ON COLUMN public.sys_tenant_entitlement.id IS '主键';
COMMENT ON COLUMN public.sys_tenant_entitlement.tenant_id IS '所属 tenant';
COMMENT ON COLUMN public.sys_tenant_entitlement.feature_code IS '功能模块码';
COMMENT ON COLUMN public.sys_tenant_entitlement.enabled IS '是否启用';
COMMENT ON COLUMN public.sys_tenant_entitlement.granted_by_user_id IS '授权人用户 id';
COMMENT ON COLUMN public.sys_tenant_entitlement.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_tenant_entitlement.update_at IS '修改时间';
