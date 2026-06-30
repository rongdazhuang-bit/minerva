-- Insert STORGE_TYPE / LOCAL dictionary item for each workspace.

INSERT INTO public.sys_dict_item (id, dict_uuid, code, name, parent_uuid, create_at, update_at, item_sort)
SELECT
  gen_random_uuid(),
  d.id,
  'LOCAL',
  '本地存储',
  NULL,
  NOW() AT TIME ZONE 'UTC',
  NOW() AT TIME ZONE 'UTC',
  10
FROM public.sys_dict d
WHERE d.dict_code = 'STORGE_TYPE'
  AND NOT EXISTS (
    SELECT 1
    FROM public.sys_dict_item i
    WHERE i.dict_uuid = d.id
      AND i.code = 'LOCAL'
  );
