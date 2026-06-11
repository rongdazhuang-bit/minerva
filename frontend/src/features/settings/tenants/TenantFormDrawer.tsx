import { Button, Drawer, Form, Input, Radio, Space } from 'antd'
import { useCallback, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import type { SysTenantCreateBody } from '@/api/tenants'

/** Form values for create/edit tenant drawer. */
export type TenantFormValues = {
  name: string
  slug: string
  status?: boolean
  remark?: string | null
}

type Props = {
  open: boolean
  title: string
  submitting: boolean
  initial?: TenantFormValues | null
  onClose: () => void
  onSubmit: (values: SysTenantCreateBody) => Promise<void>
}

/** Right drawer for creating or editing a tenant. */
export function TenantFormDrawer({
  open,
  title,
  submitting,
  initial,
  onClose,
  onSubmit,
}: Props) {
  const { t } = useTranslation()
  const [form] = Form.useForm<TenantFormValues>()

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      name: initial?.name ?? '',
      slug: initial?.slug ?? '',
      status: initial?.status ?? true,
      remark: initial?.remark ?? null,
    })
  }, [open, initial, form])

  const handleFinish = useCallback(
    async (values: TenantFormValues) => {
      await onSubmit(values)
    },
    [onSubmit],
  )

  return (
    <Drawer
      title={title}
      width={480}
      open={open}
      onClose={onClose}
      destroyOnClose
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
        <Form.Item name="remark" label={t('tenants.remark')}>
          <Input.TextArea allowClear rows={3} placeholder={t('tenants.remarkPlaceholder')} />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
