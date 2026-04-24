import { DeleteOutlined, EditOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons'
import { Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Table, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createOcrTool,
  deleteOcrTool,
  getOcrTool,
  listOcrTools,
  patchOcrTool,
  type OcrToolCreateBody,
  type OcrToolListItem,
} from '@/api/ocrTools'
import { useAuth } from '@/app/AuthContext'
import { clearOcrSettings, readOcrSettings } from '@/features/settings/ocrSettingsStorage'
import './OcrSettingsPage.css'

const { Paragraph } = Typography

type OcrFormValues = {
  name: string
  url: string
  auth_type?: 'basic' | 'api_key'
  user_name?: string
  user_passwd?: string
  api_key?: string
  remark?: string
}

export function OcrSettingsPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const [form] = Form.useForm<OcrFormValues>()
  const [loading, setLoading] = useState(false)
  const [items, setItems] = useState<OcrToolListItem[]>([])
  const [open, setOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const authType = Form.useWatch('auth_type', form) ?? 'basic'
  const legacy = useMemo(() => readOcrSettings(), [])
  const canImportLegacy = legacy.mode === 'http' && legacy.baseUrl.trim().length > 0

  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const rows = await listOcrTools(workspaceId)
      setItems(rows)
    } catch {
      void message.error(t('common.error'))
    } finally {
      setLoading(false)
    }
  }, [t, workspaceId])

  useEffect(() => {
    void load()
  }, [load])

  const columns: ColumnsType<OcrToolListItem> = [
    {
      title: t('settings.ocrToolsName'),
      dataIndex: 'name',
      key: 'name',
      width: 220,
      ellipsis: true,
    },
    {
      title: t('settings.ocrToolsUrl'),
      dataIndex: 'url',
      key: 'url',
      width: 180,
      ellipsis: true,
    },
    {
      title: t('settings.ocrToolsAuthType'),
      dataIndex: 'auth_type',
      key: 'auth_type',
      width: 140,
      render: (value: string | null) => {
        if (value === 'api_key') return 'API Key'
        if (value === 'basic') return 'basic'
        return '-'
      },
    },
    {
      title: t('settings.ocrToolsRemark'),
      dataIndex: 'remark',
      key: 'remark',
      width: 360,
      ellipsis: true,
    },
    {
      title: t('settings.ocrToolsActions'),
      key: 'actions',
      width: 140,
      render: (_, row) => (
        <Space>
          <Button
            type="text"
            icon={<EditOutlined />}
            onClick={() => void openEdit(row.id)}
            aria-label={t('settings.ocrToolsEdit')}
          />
          <Popconfirm
            title={t('settings.ocrToolsDeleteConfirm')}
            onConfirm={() => void handleDelete(row.id)}
          >
            <Button
              type="text"
              danger
              icon={<DeleteOutlined />}
              aria-label={t('settings.ocrToolsDelete')}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const openCreate = () => {
    setEditingId(null)
    form.resetFields()
    form.setFieldsValue({ auth_type: 'basic' })
    setOpen(true)
  }

  const openEdit = async (toolId: string) => {
    if (!workspaceId) return
    setEditingId(toolId)
    setSubmitting(true)
    try {
      const detail = await getOcrTool(workspaceId, toolId)
      form.setFieldsValue({
        name: detail.name,
        url: detail.url,
        auth_type: detail.auth_type === 'api_key' ? 'api_key' : 'basic',
        user_name: detail.user_name ?? '',
        user_passwd: detail.user_passwd ?? '',
        api_key: detail.api_key ?? '',
        remark: detail.remark ?? '',
      })
      setOpen(true)
    } catch {
      void message.error(t('common.error'))
    } finally {
      setSubmitting(false)
    }
  }

  const buildPayload = (values: OcrFormValues): OcrToolCreateBody => {
    const authType = values.auth_type ?? 'basic'
    const isBasic = authType === 'basic'
    return {
      name: values.name.trim(),
      url: values.url.trim(),
      auth_type: authType,
      user_name: isBasic ? values.user_name?.trim() || null : null,
      user_passwd: isBasic ? values.user_passwd?.trim() || null : null,
      api_key: authType === 'api_key' ? values.api_key?.trim() || null : null,
      remark: values.remark?.trim() || null,
    }
  }

  const onSubmit = async (values: OcrFormValues) => {
    if (!workspaceId) return
    const payload = buildPayload(values)
    setSubmitting(true)
    try {
      if (editingId) {
        await patchOcrTool(workspaceId, editingId, payload)
        void message.success(t('settings.ocrToolsUpdated'))
      } else {
        await createOcrTool(workspaceId, payload)
        void message.success(t('settings.ocrToolsCreated'))
      }
      setOpen(false)
      await load()
    } catch {
      void message.error(t('common.error'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (toolId: string) => {
    if (!workspaceId) return
    try {
      await deleteOcrTool(workspaceId, toolId)
      void message.success(t('settings.ocrToolsDeleted'))
      await load()
    } catch {
      void message.error(t('common.error'))
    }
  }

  const handleImportLegacy = async () => {
    if (!workspaceId || !canImportLegacy) return
    try {
      await createOcrTool(workspaceId, {
        name: t('settings.ocrImportDefaultName'),
        url: legacy.baseUrl.trim(),
        auth_type: legacy.apiKey.trim() ? 'api_key' : 'none',
        api_key: legacy.apiKey.trim() || null,
        remark: t('settings.ocrImportRemark'),
      })
      clearOcrSettings()
      void message.success(t('settings.ocrImportDone'))
      await load()
    } catch {
      void message.error(t('common.error'))
    }
  }

  if (!workspaceId) {
    return (
      <div className="minerva-ocr-settings">
        <Paragraph>{t('settings.ocrNoWorkspace')}</Paragraph>
      </div>
    )
  }

  return (
    <div className="minerva-ocr-settings">
      <Card size="small" variant="borderless" className="minerva-ocr-settings__card">
        <Space className="minerva-ocr-settings__toolbar">
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {t('settings.ocrToolsAdd')}
          </Button>
          {canImportLegacy ? (
            <Button icon={<UploadOutlined />} onClick={() => void handleImportLegacy()}>
              {t('settings.ocrImportLocal')}
            </Button>
          ) : null}
        </Space>

        <div className="minerva-ocr-settings__table-wrap">
          <Table<OcrToolListItem>
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={items}
            pagination={false}
            size="middle"
            className="minerva-ocr-settings__table"
            scroll={{ x: true, y: 'calc(100dvh - 320px)' }}
            sticky
          />
        </div>
      </Card>

      <Modal
        open={open}
        title={editingId ? t('settings.ocrToolsEdit') : t('settings.ocrToolsAdd')}
        onCancel={() => setOpen(false)}
        onOk={() => void form.submit()}
        confirmLoading={submitting}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={(values) => void onSubmit(values)}>
          <Form.Item
            name="name"
            label={t('settings.ocrToolsName')}
            rules={[{ required: true, message: t('settings.ocrToolsNameRequired') }]}
          >
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item
            name="url"
            label={t('settings.ocrToolsUrl')}
            rules={[
              { required: true, message: t('settings.ocrErrorUrl') },
              { type: 'url', message: t('settings.ocrErrorUrl') },
            ]}
          >
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="auth_type" label={t('settings.ocrToolsAuthType')} initialValue="basic">
            <Select
              options={[
                { value: 'basic', label: 'basic' },
                { value: 'api_key', label: 'API Key' },
              ]}
            />
          </Form.Item>
          {authType === 'basic' ? (
            <>
              <Form.Item
                name="user_name"
                label={t('settings.ocrToolsUsername')}
                rules={[{ required: true, message: t('settings.ocrToolsUsernameRequired') }]}
              >
                <Input maxLength={64} />
              </Form.Item>
              <Form.Item
                name="user_passwd"
                label={t('settings.ocrToolsPassword')}
                rules={[{ required: true, message: t('settings.ocrToolsPasswordRequired') }]}
              >
                <Input.Password maxLength={128} />
              </Form.Item>
            </>
          ) : null}
          {authType === 'api_key' ? (
            <Form.Item
              name="api_key"
              label={t('settings.ocrToolsApiKey')}
              rules={[{ required: true, message: t('settings.ocrToolsApiKeyRequired') }]}
            >
              <Input.Password maxLength={128} />
            </Form.Item>
          ) : null}
          <Form.Item name="remark" label={t('settings.ocrToolsRemark')}>
            <Input maxLength={128} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
