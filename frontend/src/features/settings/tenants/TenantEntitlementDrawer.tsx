import { Checkbox, Drawer, Form, Input, Space, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  getTenantAdmins,
  getTenantEntitlements,
  putTenantAdmins,
  putTenantEntitlements,
  TENANT_FEATURE_OPTIONS,
} from '@/api/tenantEntitlements'
import type { SysTenantListItem } from '@/api/tenants'
import { showAppError, useAppMessage } from '@/app/useAppMessage'

type Props = {
  open: boolean
  tenant: SysTenantListItem | null
  onClose: () => void
  onSaved: () => void
}

type FormValues = {
  feature_codes: string[]
  admin_user_ids: string
}

/** Drawer for super-admin tenant feature entitlements and administrator ids. */
export function TenantEntitlementDrawer({ open, tenant, onClose, onSaved }: Props) {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const [form] = Form.useForm<FormValues>()
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open || !tenant) return
    let cancelled = false
    setLoading(true)
    Promise.all([getTenantEntitlements(tenant.id), getTenantAdmins(tenant.id)])
      .then(([ent, admins]) => {
        if (cancelled) return
        form.setFieldsValue({
          feature_codes: ent.feature_codes,
          admin_user_ids: admins.user_ids.join('\n'),
        })
      })
      .catch((e) => showAppError(messageApi, t, e))
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, tenant, form, messageApi])

  const handleSubmit = async () => {
    if (!tenant) return
    const values = await form.validateFields()
    const userIds = values.admin_user_ids
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter(Boolean)
    setSubmitting(true)
    try {
      await putTenantEntitlements(tenant.id, values.feature_codes ?? [])
      await putTenantAdmins(tenant.id, userIds)
      messageApi.success(t('entitlements.saved'))
      onSaved()
      onClose()
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Drawer
      title={t('entitlements.drawerTitle', { name: tenant?.name ?? '' })}
      open={open}
      onClose={onClose}
      width={480}
      destroyOnClose
      loading={loading}
      extra={
        <Space>
          <Typography.Link onClick={onClose}>{t('tenants.cancel')}</Typography.Link>
          <Typography.Link onClick={() => void handleSubmit()} disabled={submitting}>
            {t('tenants.save')}
          </Typography.Link>
        </Space>
      }
    >
      <Form form={form} layout="vertical">
        <Form.Item name="feature_codes" label={t('entitlements.featuresLabel')}>
          <Checkbox.Group
            options={TENANT_FEATURE_OPTIONS.map((o) => ({
              label: t(o.labelKey),
              value: o.value,
            }))}
            style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
          />
        </Form.Item>
        <Form.Item
          name="admin_user_ids"
          label={t('entitlements.adminsLabel')}
          extra={t('entitlements.adminsHint')}
        >
          <Input.TextArea rows={4} placeholder={t('entitlements.adminsPlaceholder')} />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
