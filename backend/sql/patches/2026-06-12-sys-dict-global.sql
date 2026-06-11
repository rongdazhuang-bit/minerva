-- sys_dict: workspace scope -> platform global
ALTER TABLE public.sys_dict DROP CONSTRAINT IF EXISTS uq_sys_dict_workspace_dict_code;
ALTER TABLE public.sys_dict DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE public.sys_dict
  ADD CONSTRAINT uq_sys_dict_dict_code UNIQUE (dict_code);
