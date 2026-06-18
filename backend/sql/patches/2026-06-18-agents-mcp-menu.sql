INSERT INTO public.sys_menu (
  id, parent_id, menu_name, i18n_key, menu_key, order_num, path, menu_type, icon, visible, status
) VALUES (
  '9b33ab71-4f11-58e3-bf70-82bf723434ac',
  '32cbc24c-39cf-58de-966a-0e3befbc3f4e',
  'MCP', 'nav.agentsMcp', 'agents-mcp', 4,
  '/app/agents/mcp', 'C', 'ApiOutlined', true, true
) ON CONFLICT (id) DO NOTHING;
