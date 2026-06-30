-- Insert MODEL_TAG / MULTIMODAL dictionary item for each workspace (no sys_models.tags migration).

INSERT INTO public.sys_dict_item (id, dict_uuid, code, name, parent_uuid, create_at, update_at, item_sort)
SELECT
  gen_random_uuid(),
  d.id,
  'MULTIMODAL',
  '多模态',
  NULL,
  NOW() AT TIME ZONE 'UTC',
  NOW() AT TIME ZONE 'UTC',
  6
FROM public.sys_dict d
WHERE d.dict_code = 'MODEL_TAG'
  AND NOT EXISTS (
    SELECT 1
    FROM public.sys_dict_item i
    WHERE i.dict_uuid = d.id
      AND i.code = 'MULTIMODAL'
  );
