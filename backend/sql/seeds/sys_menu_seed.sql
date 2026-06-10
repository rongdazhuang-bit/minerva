-- 初始侧栏菜单（UUID v5，由 menu_key + 固定 namespace 确定性生成）
-- namespace: 19b42737-9dbb-5ed2-a61e-2171e051246d
-- 若曾导入旧版顺序 UUID，请先: DELETE FROM public.sys_menu;
INSERT INTO public.sys_menu (
  id, parent_id, menu_name, i18n_key, menu_key, order_num, path, menu_type, icon, visible, status
) VALUES
  ('74a1956f-52e0-52e9-a027-cdb9c291d672', NULL, '概览', 'nav.overview', 'overview', 1, '/app/overview', 'C', 'BarChartOutlined', true, true),
  ('32cbc24c-39cf-58de-966a-0e3befbc3f4e', NULL, '智能体', 'nav.agents', 'sub-agents', 2, NULL, 'M', 'RobotOutlined', true, true),
  ('b2088a3b-256b-52e6-8a72-c409cba808ea', '32cbc24c-39cf-58de-966a-0e3befbc3f4e', '对话', 'nav.agentsChat', 'agents-chat', 1, '/app/agents/chat', 'C', 'CommentOutlined', true, true),
  ('bb8fdcd0-157f-5b7b-acee-636b594e7014', '32cbc24c-39cf-58de-966a-0e3befbc3f4e', '技能', 'nav.agentsSkills', 'agents-skills', 2, '/app/agents/skills', 'C', 'ThunderboltOutlined', true, true),
  ('f5799b75-01ae-54bb-b959-72f0d4ee51b1', '32cbc24c-39cf-58de-966a-0e3befbc3f4e', '记忆', 'nav.agentsMemory', 'agents-memory', 3, '/app/agents/memory', 'C', 'DatabaseOutlined', true, true),
  ('15a93c9c-85d7-5f2c-b87e-10a0a9c4cbbb', NULL, '文档翻译', 'nav.docTranslate', 'sub-doc-translate', 3, NULL, 'M', 'TranslationOutlined', true, true),
  ('bf81af51-cf7d-5567-b78e-506b9ff82c8a', '15a93c9c-85d7-5f2c-b87e-10a0a9c4cbbb', '翻译', 'nav.docTranslateTranslate', 'doc-translate-translate', 1, '/app/translate', 'C', 'FileTextOutlined', true, true),
  ('80cc9a4f-f39b-564e-b3ac-158afc9ab79e', NULL, '知识库', 'nav.knowledgeBase', 'sub-dataset', 4, NULL, 'M', 'ReadOutlined', true, true),
  ('db91f71f-90aa-5ccf-9ed3-a76c6790ba06', '80cc9a4f-f39b-564e-b3ac-158afc9ab79e', '数据集', 'nav.dataset', 'dataset-list', 1, '/app/dataset', 'C', 'UnorderedListOutlined', true, true),
  ('bc61b69c-6442-51ae-a118-ec26ff90cc17', NULL, '智能审核', 'nav.smartReview', 'sub-smart-review', 5, NULL, 'M', 'FileSearchOutlined', true, true),
  ('4a6b39d1-9baf-5a1d-8c5b-f03ea4ca176e', 'bc61b69c-6442-51ae-a118-ec26ff90cc17', '文本校对', 'nav.smartReviewTextProofreading', 'smart-review-text-proofreading', 1, '/app/smart-review/text-proofreading', 'C', 'FileTextOutlined', true, true),
  ('41015668-38c7-5d37-a3d5-fd54764b6218', 'bc61b69c-6442-51ae-a118-ec26ff90cc17', '以文审文', 'nav.smartReviewTextToText', 'smart-review-text-to-text', 2, '/app/smart-review/review-by-text', 'C', 'AuditOutlined', true, true),
  ('dad4d118-76d6-51f4-8f9b-4fcd4b74333c', 'bc61b69c-6442-51ae-a118-ec26ff90cc17', '图纸审核', 'nav.smartReviewDrawingReview', 'smart-review-drawing-review', 3, '/app/smart-review/drawing-review', 'C', 'PictureOutlined', true, true),
  ('e67eecb6-fd62-5fc1-9d2f-e3759d3d0053', NULL, '规则', 'nav.rules', 'sub-rules', 6, NULL, 'M', 'BookOutlined', true, true),
  ('5721694a-ae6a-5bb1-9fe1-887321bb0130', 'e67eecb6-fd62-5fc1-9d2f-e3759d3d0053', '概览', 'nav.rulesOverview', 'rules-overview', 1, '/app/rules/overview', 'C', 'DashboardOutlined', true, true),
  ('81dce04e-45ea-54da-8e0b-fdf69c317559', 'e67eecb6-fd62-5fc1-9d2f-e3759d3d0053', '规则列表', 'nav.rulesManagementList', 'rules-mgmt-list', 2, '/app/rules/management', 'C', 'UnorderedListOutlined', true, true),
  ('c2c4da5d-01b9-5e20-92c0-5dd107854119', 'e67eecb6-fd62-5fc1-9d2f-e3759d3d0053', '配置', 'nav.rulesConfig', 'sub-rules-config', 3, NULL, 'M', 'SlidersOutlined', true, true),
  ('087d719d-7563-5712-a927-dc038549d8d1', 'c2c4da5d-01b9-5e20-92c0-5dd107854119', '提示词管理', 'nav.rulesPromptManagement', 'rules-config-config-prompts', 1, '/app/rules/config/config-prompts', 'C', 'ApiOutlined', true, true),
  ('497a5510-7536-58cf-bab3-f6645ae55117', NULL, '文件 OCR', 'nav.rulesFileOcr', 'sub-file-ocr', 7, NULL, 'M', 'ScanOutlined', true, true),
  ('3664128e-fe69-5db1-97b5-679354dbdbc9', '497a5510-7536-58cf-bab3-f6645ae55117', '概览', 'nav.rulesFileOcrOverview', 'file-ocr-overview', 1, '/app/file-ocr/overview', 'C', 'DashboardOutlined', true, true),
  ('dce7dabc-fff1-5bbe-8e39-848e408b29ae', '497a5510-7536-58cf-bab3-f6645ae55117', '任务列表', 'nav.rulesFileOcrTaskList', 'file-ocr-tasks', 2, '/app/file-ocr/tasks', 'C', 'UnorderedListOutlined', true, true),
  ('2f899ad8-d7d2-5be5-bf63-feeb426c0bb9', NULL, '设置', 'nav.settings', 'sub-settings', 8, NULL, 'M', 'SettingOutlined', true, true),
  ('be06439d-56b5-5e23-abb1-038cdfd4a879', '2f899ad8-d7d2-5be5-bf63-feeb426c0bb9', '模型供应商', 'settings.models', 'settings-models', 1, '/app/settings/models', 'C', 'ApiOutlined', true, true),
  ('d2d10aa9-d66a-51dd-a655-44659bb90bde', '2f899ad8-d7d2-5be5-bf63-feeb426c0bb9', 'OCR 工具', 'settings.ocr', 'settings-ocr', 2, '/app/settings/ocr', 'C', 'FileTextOutlined', true, true),
  ('28b60cc7-5537-5a1f-b9cf-6764103b8879', '2f899ad8-d7d2-5be5-bf63-feeb426c0bb9', '文件存储', 'settings.fileStorage', 'settings-file-storage', 3, '/app/settings/file-storage', 'C', 'FolderOpenOutlined', true, true),
  ('1f1e117d-0c66-5a9f-bd21-317f608d9675', '2f899ad8-d7d2-5be5-bf63-feeb426c0bb9', '任务调度', 'settings.celery', 'settings-celery', 4, '/app/settings/celery', 'C', 'ClockCircleOutlined', true, true),
  ('e73ee78f-abe8-5f10-a581-281e6504e479', '2f899ad8-d7d2-5be5-bf63-feeb426c0bb9', '数据源', 'settings.dataSources', 'settings-data-sources', 5, '/app/settings/data-sources', 'C', 'DatabaseOutlined', true, true),
  ('c9a908a4-fc2c-5c07-ada4-56760bb9ef43', '2f899ad8-d7d2-5be5-bf63-feeb426c0bb9', '菜单配置', 'settings.menuConfig', 'settings-menus', 6, '/app/settings/menus', 'C', 'MenuOutlined', true, true),
  ('b137ea34-f040-53f4-bf4e-f3c009e191a3', '2f899ad8-d7d2-5be5-bf63-feeb426c0bb9', '用户管理', 'settings.users', 'settings-users', 7, '/app/settings/users', 'C', 'UserOutlined', true, true),
  ('978c6b53-797a-5455-8728-3d97d2ea0619', '2f899ad8-d7d2-5be5-bf63-feeb426c0bb9', '角色管理', 'settings.roles', 'settings-roles', 8, '/app/settings/roles', 'C', 'IdcardOutlined', true, true),
  ('5a769206-f9bf-5ddd-b4f4-956d40dbc3c9', '2f899ad8-d7d2-5be5-bf63-feeb426c0bb9', '数据字典', 'settings.dictionary', 'settings-dictionary', 9, '/app/settings/dictionary', 'C', 'TagsOutlined', true, true)
ON CONFLICT (id) DO NOTHING;
