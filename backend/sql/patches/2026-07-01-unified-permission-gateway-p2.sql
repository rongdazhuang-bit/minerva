-- P2: backfill sys_user_grant from legacy sys_user_role (idempotent)
-- Apply: psql -U minerva -d minerva -f backend/sql/patches/2026-07-01-unified-permission-gateway-p2.sql

INSERT INTO public.sys_user_grant (
  id,
  user_id,
  grant_type,
  role_id,
  permission_id,
  scope_type,
  scope_id,
  granted_by_user_id,
  status,
  create_at,
  update_at
)
SELECT
  gen_random_uuid(),
  ur.user_id,
  'role',
  ur.role_id,
  NULL,
  'workspace',
  r.workspace_id,
  ur.user_id,
  true,
  COALESCE(r.create_at, now()),
  r.update_at
FROM public.sys_user_role ur
JOIN public.sys_role r ON r.id = ur.role_id
WHERE NOT EXISTS (
  SELECT 1
  FROM public.sys_user_grant g
  WHERE g.user_id = ur.user_id
    AND g.grant_type = 'role'
    AND g.role_id = ur.role_id
    AND g.scope_type = 'workspace'
    AND g.scope_id = r.workspace_id
);
