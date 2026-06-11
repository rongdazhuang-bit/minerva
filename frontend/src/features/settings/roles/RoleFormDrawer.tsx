import { Button, Checkbox, Drawer, Form, Input, InputNumber, Radio, Space, Tree } from 'antd'
import type { DataNode } from 'antd/es/tree'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SysMenuNode } from '@/api/menus'
import type { SysRoleCreateBody } from '@/api/roles'

/** Form values for create/edit role drawer. */
export type RoleFormValues = {
  role_name: string
  role_key: string
  role_sort?: number | null
  status?: boolean
  remark?: string | null
}

type Props = {
  open: boolean
  title: string
  submitting: boolean
  menuTree: SysMenuNode[]
  initial?: RoleFormValues | null
  initialMenuIds?: string[]
  onClose: () => void
  onSubmit: (values: SysRoleCreateBody) => Promise<void>
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

/** Right drawer for creating or editing a workspace role and menu permissions. */
export function RoleFormDrawer({
  open,
  title,
  submitting,
  menuTree,
  initial,
  initialMenuIds,
  onClose,
  onSubmit,
}: Props) {
  const { t } = useTranslation()
  const [form] = Form.useForm<RoleFormValues>()
  const [checkedKeys, setCheckedKeys] = useState<string[]>([])
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const [expandAll, setExpandAll] = useState(false)
  const [checkStrictly, setCheckStrictly] = useState(false)

  const treeData = useMemo(() => buildTreeData(menuTree), [menuTree])
  const allKeys = useMemo(() => collectAllKeys(menuTree), [menuTree])

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      role_name: initial?.role_name ?? '',
      role_key: initial?.role_key ?? '',
      role_sort: initial?.role_sort ?? 0,
      status: initial?.status ?? true,
      remark: initial?.remark ?? null,
    })
    setCheckedKeys(initialMenuIds ?? [])
    setExpandedKeys([])
    setExpandAll(false)
    setCheckStrictly(false)
  }, [open, initial, initialMenuIds, form])

  useEffect(() => {
    setExpandedKeys(expandAll ? allKeys : [])
  }, [expandAll, allKeys])

  const handleFinish = useCallback(
    async (values: RoleFormValues) => {
      await onSubmit({
        role_name: values.role_name.trim(),
        role_key: values.role_key.trim(),
        role_sort: values.role_sort ?? 0,
        status: values.status ?? true,
        remark: values.remark?.trim() || null,
        menu_ids: checkedKeys,
      })
    },
    [checkedKeys, onSubmit],
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
                borderRadius: 6,
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
