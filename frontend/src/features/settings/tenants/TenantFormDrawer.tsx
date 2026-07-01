import { Button, Drawer, Form, Input, Radio, Space } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SysMenuNode } from '@/api/menus'
import {
  getTenantAdmins,
  getTenantPermissions,
  listPlatformUserOptions,
  listTenantPermissionMenuTree,
  listTenantUsers,
} from '@/api/tenantPermissions'
import type { SysTenantCreateBody } from '@/api/tenants'
import { showAppError, useAppMessage } from '@/app/useAppMessage'
import { buildTenantAdminSelectOptions } from './tenantAdminOptions'
import { TenantPermissionFields } from './TenantPermissionFields'

/** Form values for create/edit tenant drawer. */
export type TenantFormValues = {
  name: string
  slug: string
  status?: boolean
  remark?: string | null
  admin_user_ids?: string[]
}

/** Menu permissions and administrators saved with tenant create/edit. */
export type TenantCreatePermissions = {
  menu_ids: string[]
  admin_user_ids: string[]
}

type Props = {
  open: boolean
  title: string
  mode: 'create' | 'edit'
  tenantId?: string | null
  submitting: boolean
  initial?: TenantFormValues | null
  onClose: () => void
  onSubmit: (
    values: SysTenantCreateBody,
    permissions: TenantCreatePermissions,
  ) => Promise<void>
}

/** Right drawer for creating or editing a tenant with menu permissions. */
export function TenantFormDrawer({
  open,
  title,
  mode,
  tenantId,
  submitting,
  initial,
  onClose,
  onSubmit,
}: Props) {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const [form] = Form.useForm<TenantFormValues>()
  const [permissionLoading, setPermissionLoading] = useState(false)
  const [menuTree, setMenuTree] = useState<SysMenuNode[]>([])
  const [checkedKeys, setCheckedKeys] = useState<string[]>([])
  const [userOptions, setUserOptions] = useState<{ value: string; label: string }[]>([])

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      name: initial?.name ?? '',
      slug: initial?.slug ?? '',
      status: initial?.status ?? true,
      remark: initial?.remark ?? null,
      admin_user_ids: [],
    })
    setCheckedKeys([])

    let cancelled = false
    setPermissionLoading(true)

    const orphanLabel = (id: string) => t('permissions.adminOrphanLabel', { id })

    const loadPromise =
      mode === 'edit' && tenantId
        ? Promise.all([
            getTenantPermissions(tenantId),
            getTenantAdmins(tenantId),
            listTenantUsers(tenantId),
            listTenantPermissionMenuTree(),
          ]).then(([permissions, admins, users, tree]) => {
            if (cancelled) return
            setMenuTree(tree)
            setCheckedKeys(permissions.menu_ids)
            form.setFieldsValue({ admin_user_ids: admins.user_ids })
            setUserOptions(
              buildTenantAdminSelectOptions(users.items, admins.user_ids, orphanLabel),
            )
          })
        : Promise.all([listTenantPermissionMenuTree(), listPlatformUserOptions()]).then(
            ([tree, users]) => {
              if (cancelled) return
              setMenuTree(tree)
              setUserOptions(
                users.items.map((u) => ({
                  value: u.id,
                  label: `${u.nickname} (${u.email})`,
                })),
              )
            },
          )

    loadPromise
      .catch((e) => showAppError(messageApi, t, e))
      .finally(() => {
        if (!cancelled) setPermissionLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [open, initial, mode, tenantId, form, messageApi, t])

  const handleFinish = useCallback(
    async (values: TenantFormValues) => {
      const body: SysTenantCreateBody = {
        name: values.name.trim(),
        slug: values.slug.trim(),
        status: values.status ?? true,
        remark: values.remark?.trim() || null,
      }
      await onSubmit(body, {
        menu_ids: checkedKeys,
        admin_user_ids: values.admin_user_ids ?? [],
      })
    },
    [checkedKeys, onSubmit],
  )

  return (
    <Drawer
      title={title}
      width={520}
      open={open}
      onClose={onClose}
      destroyOnClose
      loading={permissionLoading}
      footer={null}
      classNames={{ body: 'minerva-scrollbar-styled' }}
      extra={
        <Space>
          <Button onClick={onClose} disabled={submitting}>
            {t('tenants.cancel')}
          </Button>
          <Button type="primary" loading={submitting} onClick={() => void form.submit()}>
            {t('tenants.save')}
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical" onFinish={handleFinish}>
        <Form.Item
          name="name"
          label={t('tenants.tenantName')}
          rules={[{ required: true, message: t('tenants.tenantNameRequired') }]}
        >
          <Input allowClear placeholder={t('tenants.tenantNamePlaceholder')} />
        </Form.Item>
        <Form.Item
          name="slug"
          label={t('tenants.slug')}
          rules={[{ required: true, message: t('tenants.slugRequired') }]}
        >
          <Input allowClear placeholder={t('tenants.slugPlaceholder')} />
        </Form.Item>
        <Form.Item name="status" label={t('tenants.status')} rules={[{ required: true }]}>
          <Radio.Group>
            <Radio value={true}>{t('tenants.statusNormal')}</Radio>
            <Radio value={false}>{t('tenants.statusDisabled')}</Radio>
          </Radio.Group>
        </Form.Item>
        <TenantPermissionFields
          menuTree={menuTree}
          checkedKeys={checkedKeys}
          onCheckedKeysChange={setCheckedKeys}
          userOptions={userOptions}
          adminsHint={
            mode === 'create'
              ? t('permissions.adminsHintCreate')
              : t('permissions.adminsHint')
          }
        />
        <Form.Item name="remark" label={t('tenants.remark')}>
          <Input.TextArea allowClear rows={3} placeholder={t('tenants.remarkPlaceholder')} />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
