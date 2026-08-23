-- GraphKB feature entitlement + sidebar menus (idempotent)
-- Apply: psql -U minerva -d minerva -f backend/sql/patches/2026-08-23-graph-kb-feature-menu.sql

-- 1) Feature permission code
INSERT INTO public.sys_permission (id, perm_code, perm_name, perm_type, status, create_at)
SELECT gen_random_uuid(), v.perm_code, v.perm_name, v.perm_type, true, now()
FROM (
  VALUES
    ('feature:graph_kb', '知识图谱模块', 'feature')
) AS v(perm_code, perm_name, perm_type)
WHERE NOT EXISTS (
  SELECT 1 FROM public.sys_permission p WHERE p.perm_code = v.perm_code
);

-- 2) Sidebar menus (UUID v5 from menu_key + fixed namespace)
INSERT INTO public.sys_menu (
  id, parent_id, menu_name, i18n_key, menu_key, order_num, path, menu_type, icon, visible, status
) VALUES
  (
    '89803e0d-3455-5602-9bdd-55e138974154',
    NULL,
    '知识图谱', 'nav.graphKb', 'sub-graph-kb', 5,
    NULL, 'M', 'ApartmentOutlined', true, true
  ),
  (
    '13c654eb-10eb-524e-9f00-ef1cfb08ac62',
    '89803e0d-3455-5602-9bdd-55e138974154',
    '图谱', 'nav.graphKbList', 'graph-kb-list', 1,
    '/app/graph-kb', 'C', 'ApartmentOutlined', true, true
  )
ON CONFLICT (id) DO NOTHING;

-- 3) Menu-typed permissions for the new rows
INSERT INTO public.sys_permission (
  id,
  perm_code,
  perm_name,
  perm_type,
  menu_id,
  status,
  create_at
)
SELECT
  gen_random_uuid(),
  'menu:' || COALESCE(NULLIF(TRIM(m.menu_key), ''), m.id::text),
  m.menu_name,
  'menu',
  m.id,
  m.status,
  COALESCE(m.create_at, now())
FROM public.sys_menu m
WHERE m.menu_key IN ('sub-graph-kb', 'graph-kb-list')
  AND NOT EXISTS (
    SELECT 1 FROM public.sys_permission p WHERE p.menu_id = m.id
  );
