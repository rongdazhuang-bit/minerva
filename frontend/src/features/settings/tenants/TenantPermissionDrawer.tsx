import { Button, Drawer, Form, Space } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SysMenuNode } from '@/api/menus'
import {
  getTenantAdmins,
  getTenantPermissions,
  listTenantPermissionMenuTree,
  listTenantUsers,
  putTenantAdmins,
  putTenantPermissions,
} from '@/api/tenantPermissions'
import type { SysTenantListItem } from '@/api/tenants'
import { showAppError, useAppMessage } from '@/app/useAppMessage'
import { buildTenantAdminSelectOptions } from './tenantAdminOptions'
import { TenantPermissionFields } from './TenantPermissionFields'

type Props = {
  open: boolean
  tenant: SysTenantListItem | null
  onClose: () => void
  onSaved: () => void
}

type FormValues = {
  admin_user_ids: string[]
}

/** Drawer for super-admin tenant menu permissions and administrator multi-select. */
export function TenantPermissionDrawer({ open, tenant, onClose, onSaved }: Props) {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const [form] = Form.useForm<FormValues>()
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [menuTree, setMenuTree] = useState<SysMenuNode[]>([])
  const [checkedKeys, setCheckedKeys] = useState<string[]>([])
  const [userOptions, setUserOptions] = useState<{ value: string; label: string }[]>([])

  useEffect(() => {
    if (!open || !tenant) return
    let cancelled = false
    setLoading(true)
    Promise.all([
      getTenantPermissions(tenant.id),
      getTenantAdmins(tenant.id),
      listTenantUsers(tenant.id),
      listTenantPermissionMenuTree(),
    ])
      .then(([permissions, admins, users, tree]) => {
        if (cancelled) return
        setMenuTree(tree)
        setCheckedKeys(permissions.menu_ids)
        form.setFieldsValue({ admin_user_ids: admins.user_ids })
        setUserOptions(
          buildTenantAdminSelectOptions(users.items, admins.user_ids, (id) =>
            t('permissions.adminOrphanLabel', { id }),
          ),
        )
      })
      .catch((e) => showAppError(messageApi, t, e))
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, tenant, form, messageApi, t])

  const handleSubmit = useCallback(async () => {
    if (!tenant) return
    const values = await form.validateFields()
    setSubmitting(true)
    try {
      await putTenantPermissions(tenant.id, checkedKeys)
      await putTenantAdmins(tenant.id, values.admin_user_ids ?? [])
      messageApi.success(t('permissions.saved'))
      onSaved()
      onClose()
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setSubmitting(false)
    }
  }, [tenant, form, checkedKeys, messageApi, t, onSaved, onClose])

  return (
    <Drawer
      title={t('permissions.drawerTitle', { name: tenant?.name ?? '' })}
      width={520}
      open={open}
      destroyOnClose
      onClose={onClose}
      loading={loading}
      footer={null}
      classNames={{ body: 'minerva-scrollbar-styled' }}
      extra={
        <Space>
          <Button onClick={onClose} disabled={submitting}>
            {t('common.cancel')}
          </Button>
          <Button type="primary" loading={submitting} onClick={() => void handleSubmit()}>
            {t('common.save')}
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical">
        <TenantPermissionFields
          menuTree={menuTree}
          checkedKeys={checkedKeys}
          onCheckedKeysChange={setCheckedKeys}
          userOptions={userOptions}
        />
      </Form>
    </Drawer>
  )
}
