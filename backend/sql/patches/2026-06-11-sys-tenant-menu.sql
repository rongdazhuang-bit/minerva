INSERT INTO public.sys_menu (
  id, parent_id, menu_name, i18n_key, menu_key, order_num, path, menu_type, icon, visible, status
) VALUES (
  'f3e8a912-4c1d-5b6a-9e7f-2d8c4a1b0e59',
  '2f899ad8-d7d2-5be5-bf63-feeb426c0bb9',
  '租户管理', 'settings.tenants', 'settings-tenants', 9,
  '/app/settings/tenants', 'C', 'BankOutlined', true, true
) ON CONFLICT (id) DO NOTHING;

UPDATE public.sys_menu
SET order_num = 10
WHERE id = '5a769206-f9bf-5ddd-b4f4-956d40dbc3c9';
