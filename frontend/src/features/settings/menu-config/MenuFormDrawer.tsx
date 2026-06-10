import { Button, Drawer, Form, Input, InputNumber, Radio, Space, Switch, TreeSelect } from 'antd'
import type { TreeSelectProps } from 'antd'
import { useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { SysMenuCreateBody, SysMenuNode } from '@/api/menus'
import { MenuIconSelect } from './MenuIconSelect'

export type MenuFormValues = {
  parent_id?: string | null
  menu_name: string
  menu_type: 'M' | 'C' | 'F'
  i18n_key?: string | null
  menu_key?: string | null
  order_num?: number | null
  path?: string | null
  perms?: string | null
  icon?: string | null
  visible?: boolean
  status?: boolean
  is_external?: boolean
  remark?: string | null
}

type Props = {
  open: boolean
  title: string
  submitting: boolean
  tree: SysMenuNode[]
  editingId: string | null
  initial?: MenuFormValues | null
  defaultParentId?: string | null
  onClose: () => void
  onSubmit: (values: SysMenuCreateBody) => Promise<void>
}

function flattenIds(nodes: SysMenuNode[], forbidden: Set<string>, out: TreeSelectProps['treeData'] = []) {
  for (const n of nodes) {
    if (forbidden.has(n.id)) continue
    const children = n.children?.length
      ? flattenIds(n.children, forbidden, [])
      : undefined
    out.push({
      title: n.menu_name,
      value: n.id,
      key: n.id,
      ...(children && children.length > 0 ? { children } : {}),
    })
  }
  return out
}

function collectDescendantIds(node: SysMenuNode): Set<string> {
  const out = new Set<string>()
  const walk = (n: SysMenuNode) => {
    for (const c of n.children ?? []) {
      out.add(c.id)
      walk(c)
    }
  }
  walk(node)
  return out
}

function findNode(nodes: SysMenuNode[], id: string): SysMenuNode | null {
  for (const n of nodes) {
    if (n.id === id) return n
    if (n.children?.length) {
      const found = findNode(n.children, id)
      if (found) return found
    }
  }
  return null
}

export function MenuFormDrawer({
  open,
  title,
  submitting,
  tree,
  editingId,
  initial,
  defaultParentId,
  onClose,
  onSubmit,
}: Props) {
  const { t } = useTranslation()
  const [form] = Form.useForm<MenuFormValues>()
  const menuType = Form.useWatch('menu_type', form) ?? 'M'

  const parentTreeData = useMemo(() => {
    const forbidden = new Set<string>()
    if (editingId) {
      forbidden.add(editingId)
      const node = findNode(tree, editingId)
      if (node) collectDescendantIds(node).forEach((id) => forbidden.add(id))
    }
    return flattenIds(tree, forbidden)
  }, [tree, editingId])

  useEffect(() => {
    if (!open) return
    form.resetFields()
    if (initial) {
      form.setFieldsValue(initial)
    } else {
      form.setFieldsValue({
        menu_type: 'M',
        order_num: 0,
        visible: true,
        status: true,
        is_external: false,
        parent_id: defaultParentId ?? null,
      })
    }
  }, [open, initial, defaultParentId, form])

  return (
    <Drawer
      title={title}
      open={open}
      width={480}
      destroyOnClose
      onClose={onClose}
      footer={null}
      classNames={{ body: 'minerva-scrollbar-styled' }}
      extra={
        <Space>
          <Button onClick={onClose} disabled={submitting}>
            {t('common.cancel')}
          </Button>
          <Button type="primary" loading={submitting} onClick={() => void form.submit()}>
            {t('common.save')}
          </Button>
        </Space>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={async (values) => {
          const body: SysMenuCreateBody = {
            parent_id: values.parent_id ?? null,
            menu_name: values.menu_name,
            menu_type: values.menu_type,
            i18n_key: values.i18n_key ?? null,
            menu_key: values.menu_key ?? null,
            order_num: values.order_num ?? 0,
            path: values.path ?? null,
            perms: values.perms ?? null,
            icon: values.icon ?? null,
            visible: values.visible ?? true,
            status: values.status ?? true,
            is_external: values.is_external ?? false,
            remark: values.remark ?? null,
          }
          await onSubmit(body)
        }}
      >
        <Form.Item name="parent_id" label={t('menuConfig.fields.parent')}>
          <TreeSelect
            allowClear
            treeData={parentTreeData}
            placeholder={t('menuConfig.fields.parentPlaceholder')}
            treeDefaultExpandAll
          />
        </Form.Item>
        <Form.Item
          name="menu_type"
          label={t('menuConfig.fields.menuType')}
          rules={[{ required: true }]}
        >
          <Radio.Group>
            <Radio value="M">{t('menuConfig.menuType.M')}</Radio>
            <Radio value="C">{t('menuConfig.menuType.C')}</Radio>
            <Radio value="F">{t('menuConfig.menuType.F')}</Radio>
          </Radio.Group>
        </Form.Item>
        <Form.Item
          name="menu_name"
          label={t('menuConfig.fields.menuName')}
          rules={[{ required: true }]}
        >
          <Input allowClear />
        </Form.Item>
        {menuType !== 'F' ? (
          <Form.Item name="i18n_key" label={t('menuConfig.fields.i18nKey')}>
            <Input allowClear placeholder="nav.overview" />
          </Form.Item>
        ) : null}
        {menuType !== 'F' ? (
          <Form.Item name="icon" label={t('menuConfig.fields.icon')}>
            <MenuIconSelect />
          </Form.Item>
        ) : null}
        <Form.Item name="order_num" label={t('menuConfig.fields.orderNum')}>
          <InputNumber style={{ width: '100%' }} />
        </Form.Item>
        {menuType === 'C' ? (
          <Form.Item
            name="path"
            label={t('menuConfig.fields.path')}
            rules={[{ required: true }]}
          >
            <Input allowClear placeholder="/app/overview" />
          </Form.Item>
        ) : null}
        {menuType === 'F' ? (
          <Form.Item
            name="perms"
            label={t('menuConfig.fields.perms')}
            rules={[{ required: true }]}
          >
            <Input allowClear />
          </Form.Item>
        ) : (
          <Form.Item name="perms" label={t('menuConfig.fields.perms')}>
            <Input allowClear />
          </Form.Item>
        )}
        {menuType !== 'F' ? (
          <Form.Item name="visible" label={t('menuConfig.fields.visible')} valuePropName="checked">
            <Switch />
          </Form.Item>
        ) : null}
        <Form.Item name="status" label={t('menuConfig.fields.status')} valuePropName="checked">
          <Switch />
        </Form.Item>
        {menuType === 'C' ? (
          <Form.Item name="is_external" label={t('menuConfig.fields.isExternal')} valuePropName="checked">
            <Switch />
          </Form.Item>
        ) : null}
        <Form.Item name="menu_key" label={t('menuConfig.fields.menuKey')}>
          <Input allowClear />
        </Form.Item>
        <Form.Item name="remark" label={t('menuConfig.fields.remark')}>
          <Input.TextArea allowClear rows={3} />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
