import {
  Alert,
  Button,
  Checkbox,
  Drawer,
  Form,
  Input,
  InputNumber,
  Radio,
  Select,
  Space,
  Tag,
  Tree,
} from 'antd'
import type { DataNode } from 'antd/es/tree'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SysMenuNode } from '@/api/menus'
import type { SysRoleCapabilities, SysRoleCreateBody, SysRolePatchBody } from '@/api/roles'

/** Form values for create/edit role drawer. */
export type RoleFormValues = {
  role_name: string
  role_key: string
  role_sort?: number | null
  status?: boolean
  remark?: string | null
  tenant_id?: string
  workspace_id?: string
}

/** Read-only scope shown when editing a role. */
export type RoleScope = {
  tenant_id: string
  tenant_name: string
  workspace_id: string
  workspace_name: string
}

type Props = {
  open: boolean
  title: string
  submitting: boolean
  mode: 'create' | 'edit'
  capabilities: SysRoleCapabilities | null
  menuTree: SysMenuNode[]
  menuTreeHint?: string | null
  initial?: RoleFormValues | null
  initialMenuIds?: string[]
  initialScope?: RoleScope | null
  tenants?: { id: string; name: string }[]
  workspaces?: { id: string; name: string }[]
  onTenantChange?: (tenantId: string) => void
  metaLoading?: boolean
  onClose: () => void
  onSubmit: (
    values: SysRoleCreateBody | SysRolePatchBody,
    context?: { tenantId?: string },
  ) => Promise<void>
}

/** Collect all node keys from a menu tree. */
function collectAllKeys(nodes: SysMenuNode[]): string[] {
  const out: string[] = []
  const walk = (items: SysMenuNode[]) => {
    for (const n of items) {
      out.push(n.id)
      if (n.children?.length) walk(n.children)
    }
  }
  walk(nodes)
  return out
}

/** Build Ant Design tree nodes from menu API tree. */
function buildTreeData(nodes: SysMenuNode[]): DataNode[] {
  return nodes.map((n) => {
    let title = n.menu_name
    if (n.menu_type === 'F' && n.perms) {
      title = `${n.menu_name} (${n.perms})`
    }
    return {
      key: n.id,
      title,
      children: n.children?.length ? buildTreeData(n.children) : undefined,
    }
  })
}

/** Right drawer for creating or editing a tenant-scoped role and menu permissions. */
export function RoleFormDrawer({
  open,
  title,
  submitting,
  mode,
  capabilities,
  menuTree,
  menuTreeHint,
  initial,
  initialMenuIds,
  initialScope,
  tenants = [],
  workspaces = [],
  onTenantChange,
  metaLoading = false,
  onClose,
  onSubmit,
}: Props) {
  const { t } = useTranslation()
  const [form] = Form.useForm<RoleFormValues>()
  const [checkedKeys, setCheckedKeys] = useState<string[]>([])
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const [expandAll, setExpandAll] = useState(false)
  const [checkStrictly, setCheckStrictly] = useState(false)
  const prevAllKeysRef = useRef('')

  const treeData = useMemo(() => buildTreeData(menuTree), [menuTree])
  const allKeys = useMemo(() => collectAllKeys(menuTree), [menuTree])

  const selectedTenantId = Form.useWatch('tenant_id', form)

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      role_name: initial?.role_name ?? '',
      role_key: initial?.role_key ?? '',
      role_sort: initial?.role_sort ?? 0,
      status: initial?.status ?? true,
      remark: initial?.remark ?? null,
      tenant_id:
        mode === 'edit' && initialScope
          ? initialScope.tenant_id
          : initial?.tenant_id ?? capabilities?.fixed_tenant_id ?? undefined,
      workspace_id:
        mode === 'edit' && initialScope
          ? initialScope.workspace_id
          : initial?.workspace_id ?? undefined,
    })
    setCheckedKeys(initialMenuIds ?? [])
    setExpandedKeys([])
    setExpandAll(false)
    setCheckStrictly(false)
  }, [open, initial, initialMenuIds, capabilities, form, mode, initialScope])

  useEffect(() => {
    setExpandedKeys(expandAll ? allKeys : [])
  }, [expandAll, allKeys])

  useEffect(() => {
    if (!open) {
      prevAllKeysRef.current = ''
      return
    }
    const key = allKeys.join(',')
    if (!prevAllKeysRef.current) {
      prevAllKeysRef.current = key
      return
    }
    if (prevAllKeysRef.current === key) return
    prevAllKeysRef.current = key
    const valid = new Set(allKeys)
    setCheckedKeys((prev) => prev.filter((id) => valid.has(id)))
  }, [allKeys, open])

  const handleFinish = useCallback(
    async (values: RoleFormValues) => {
      const base = {
        role_name: values.role_name.trim(),
        role_key: values.role_key.trim(),
        role_sort: values.role_sort ?? 0,
        status: values.status ?? true,
        remark: values.remark?.trim() || null,
        menu_ids: checkedKeys,
      }
      if (mode === 'create') {
        await onSubmit(
          {
            ...base,
            workspace_id: values.workspace_id!,
          },
          {
            tenantId:
              values.tenant_id ??
              capabilities?.fixed_tenant_id ??
              undefined,
          },
        )
        return
      }
      await onSubmit(base)
    },
    [checkedKeys, mode, onSubmit, capabilities?.fixed_tenant_id],
  )

  return (
    <Drawer
      title={title}
      width={520}
      open={open}
      destroyOnClose
      onClose={onClose}
      classNames={{ body: 'minerva-scrollbar-styled' }}
      footer={
        <Space style={{ float: 'right' }}>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="primary" loading={submitting} onClick={() => form.submit()}>
            {t('common.save')}
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical" onFinish={handleFinish}>
        {mode === 'edit' && initialScope ? (
          <>
            <Form.Item name="tenant_id" label={t('roles.tenant')}>
              <Select
                disabled
                options={[
                  {
                    value: initialScope.tenant_id,
                    label: initialScope.tenant_name,
                  },
                ]}
              />
            </Form.Item>
            <Form.Item name="workspace_id" label={t('roles.workspace')}>
              <Select
                disabled
                options={[
                  {
                    value: initialScope.workspace_id,
                    label: initialScope.workspace_name,
                  },
                ]}
              />
            </Form.Item>
          </>
        ) : null}
        {mode === 'create' ? (
          <>
            {capabilities?.can_pick_tenant ? (
              <Form.Item
                name="tenant_id"
                label={t('roles.tenant')}
                rules={[{ required: true, message: t('roles.tenant') }]}
              >
                <Select
                  allowClear={false}
                  loading={metaLoading}
                  placeholder={t('roles.tenant')}
                  options={tenants.map((row) => ({
                    value: row.id,
                    label: row.name,
                  }))}
                  onChange={(tenantId: string) => {
                    form.setFieldValue('workspace_id', undefined)
                    onTenantChange?.(tenantId)
                  }}
                />
              </Form.Item>
            ) : capabilities?.fixed_tenant_name ? (
              <Form.Item label={t('roles.tenant')}>
                <Tag>{capabilities.fixed_tenant_name}</Tag>
              </Form.Item>
            ) : null}
            <Form.Item
              name="workspace_id"
              label={t('roles.workspace')}
              rules={[{ required: true, message: t('roles.workspaceRequired') }]}
            >
              <Select
                allowClear={false}
                loading={metaLoading}
                disabled={capabilities?.can_pick_tenant && !selectedTenantId}
                placeholder={t('roles.workspace')}
                options={workspaces.map((row) => ({
                  value: row.id,
                  label: row.name,
                }))}
              />
            </Form.Item>
          </>
        ) : null}
        <Form.Item
          name="role_name"
          label={t('roles.roleName')}
          rules={[{ required: true, message: t('roles.roleNameRequired') }]}
        >
          <Input allowClear placeholder={t('roles.roleNamePlaceholder')} />
        </Form.Item>
        <Form.Item
          name="role_key"
          label={t('roles.roleKey')}
          rules={[{ required: true, message: t('roles.roleKeyRequired') }]}
        >
          <Input allowClear placeholder={t('roles.roleKeyPlaceholder')} />
        </Form.Item>
        <Form.Item
          name="role_sort"
          label={t('roles.roleSort')}
          rules={[{ required: true, message: t('roles.roleSortRequired') }]}
        >
          <InputNumber min={0} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="status" label={t('roles.status')} initialValue>
          <Radio.Group>
            <Radio value>{t('roles.statusNormal')}</Radio>
            <Radio value={false}>{t('roles.statusDisabled')}</Radio>
          </Radio.Group>
        </Form.Item>
        <Form.Item label={t('roles.menuPermissions')}>
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            {menuTree.length === 0 && menuTreeHint ? (
              <Alert type="info" showIcon message={menuTreeHint} />
            ) : null}
            <Space wrap>
              <Checkbox checked={expandAll} onChange={(e) => setExpandAll(e.target.checked)}>
                {t('roles.expandCollapse')}
              </Checkbox>
              <Checkbox
                checked={checkedKeys.length > 0 && checkedKeys.length === allKeys.length}
                indeterminate={
                  checkedKeys.length > 0 && checkedKeys.length < allKeys.length
                }
                onChange={(e) => setCheckedKeys(e.target.checked ? allKeys : [])}
              >
                {t('roles.selectAll')}
              </Checkbox>
              <Checkbox
                checked={!checkStrictly}
                onChange={(e) => setCheckStrictly(!e.target.checked)}
              >
                {t('roles.parentChildLink')}
              </Checkbox>
            </Space>
            <div
              className="minerva-scrollbar-styled"
              style={{
                border: '1px solid var(--minerva-border)',
                borderRadius: 4,
                padding: 8,
                maxHeight: 280,
                overflow: 'auto',
              }}
            >
              <Tree
                checkable
                selectable={false}
                checkStrictly={checkStrictly}
                treeData={treeData}
                expandedKeys={expandedKeys}
                checkedKeys={checkedKeys}
                onExpand={(keys) => setExpandedKeys(keys as string[])}
                onCheck={(checked) => {
                  if (Array.isArray(checked)) {
                    setCheckedKeys(checked as string[])
                  } else {
                    setCheckedKeys(checked.checked as string[])
                  }
                }}
              />
            </div>
          </Space>
        </Form.Item>
        <Form.Item name="remark" label={t('roles.remark')}>
          <Input.TextArea
            allowClear
            rows={3}
            placeholder={t('roles.remarkPlaceholder')}
            classNames={{ textarea: 'minerva-scrollbar-styled' }}
          />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
