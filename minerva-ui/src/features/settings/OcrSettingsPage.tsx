import { DeleteOutlined, EditOutlined, EyeOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons'
import {
  Button,
  Card,
  Descriptions,
  Divider,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Table,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listDictItems, listDicts, type SysDictItem } from '@/api/dicts'
import {
  createOcrTool,
  deleteOcrTool,
  getOcrTool,
  listOcrTools,
  patchOcrTool,
  type OcrToolCreateBody,
  type OcrToolDetail,
  type OcrToolListItem,
} from '@/api/ocrTools'
import { useAuth } from '@/app/AuthContext'
import {
  OCR_AUTH_API_KEY,
  OCR_AUTH_BASIC,
  OCR_AUTH_NONE,
  canonicalOcrAuthType,
  isOcrApiKeyAuth,
  isOcrBasicAuth,
  isOcrNoneAuth,
} from '@/features/settings/ocrAuthType'
import { clearOcrSettings, readOcrSettings } from '@/features/settings/ocrSettingsStorage'
import './OcrSettingsPage.css'

const { Paragraph } = Typography

/** 数据字典中 OCR 认证方式的字典编码（与「数据字典」菜单中的 dict_code 一致）。 */
const AUTH_TYPE_DICT_CODE = 'AUTH_TYPE'

type OcrFormValues = {
  name: string
  url: string
  auth_type?: string
  user_name?: string
  user_passwd?: string
  api_key?: string
  remark?: string
}

function sortDictItems(items: SysDictItem[]) {
  return [...items].sort(
    (a, b) =>
      (b.item_sort ?? 0) - (a.item_sort ?? 0) || a.code.localeCompare(b.code),
  )
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
  const [authItems, setAuthItems] = useState<SysDictItem[]>([])
  const [authDictLoading, setAuthDictLoading] = useState(false)
  const [viewOpen, setViewOpen] = useState(false)
  const [viewLoading, setViewLoading] = useState(false)
  const [viewDetail, setViewDetail] = useState<OcrToolDetail | null>(null)

  const watchedAuthType = Form.useWatch('auth_type', form)
  const legacy = useMemo(() => readOcrSettings(), [])
  const canImportLegacy = legacy.mode === 'http' && legacy.baseUrl.trim().length > 0

  const loadAuthDict = useCallback(async () => {
    if (!workspaceId) return
    setAuthDictLoading(true)
    try {
      const dicts = await listDicts(workspaceId)
      const d = dicts.find((row) => row.dict_code === AUTH_TYPE_DICT_CODE)
      if (!d) {
        setAuthItems([])
        return
      }
      const rows = await listDictItems(workspaceId, d.id)
      setAuthItems(rows)
    } catch {
      setAuthItems([])
    } finally {
      setAuthDictLoading(false)
    }
  }, [workspaceId])

  useEffect(() => {
    void loadAuthDict()
  }, [loadAuthDict])

  const baseAuthSelectOptions = useMemo(() => {
    const sorted = sortDictItems(authItems)
    if (sorted.length > 0) {
      return sorted.map((i) => ({ value: i.code, label: i.name }))
    }
    return [
      { value: OCR_AUTH_NONE, label: t('settings.ocrAuthTypeDictNone') },
      { value: OCR_AUTH_BASIC, label: t('settings.ocrAuthTypeDictBasic') },
      { value: OCR_AUTH_API_KEY, label: t('settings.ocrAuthTypeDictApiKey') },
    ]
  }, [authItems, t])

  const authLabelByCode = useMemo(() => {
    const m = new Map<string, string>()
    for (const i of sortDictItems(authItems)) {
      m.set(i.code, i.name)
    }
    const noneL = t('settings.ocrAuthTypeDictNone')
    const basicL = t('settings.ocrAuthTypeDictBasic')
    const apiL = t('settings.ocrAuthTypeDictApiKey')
    if (m.size === 0) {
      m.set(OCR_AUTH_NONE, noneL)
      m.set(OCR_AUTH_BASIC, basicL)
      m.set(OCR_AUTH_API_KEY, apiL)
    }
    m.set('none', noneL)
    m.set('basic', basicL)
    m.set('api_key', apiL)
    return m
  }, [authItems, t])

  const authSelectOptions = useMemo(() => {
    if (!open) return baseAuthSelectOptions
    const cur = watchedAuthType
    if (cur != null && cur !== '' && !baseAuthSelectOptions.some((o) => o.value === cur)) {
      return [...baseAuthSelectOptions, { value: cur, label: cur }]
    }
    return baseAuthSelectOptions
  }, [baseAuthSelectOptions, open, watchedAuthType])

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

  useEffect(() => {
    if (!open || editingId) return
    if (baseAuthSelectOptions.length === 0) return
    const cur = form.getFieldValue('auth_type') as string | undefined
    if (cur != null && baseAuthSelectOptions.some((o) => o.value === cur)) return
    const next =
      baseAuthSelectOptions.find((o) => o.value === OCR_AUTH_BASIC) ??
      baseAuthSelectOptions[0]
    form.setFieldsValue({ auth_type: next?.value })
  }, [open, editingId, baseAuthSelectOptions, form])

  const resolveAuthLabel = (code: string | null) => {
    if (code == null || code === '') return '—'
    const exact = authLabelByCode.get(code)
    if (exact) return exact
    const canon = canonicalOcrAuthType(code)
    return authLabelByCode.get(canon) ?? code
  }

  const formatDateTime = (v: string | null | undefined) =>
    v ? new Date(v).toLocaleString(undefined, { hour12: false }) : '—'

  const openView = async (toolId: string) => {
    if (!workspaceId) return
    setViewOpen(true)
    setViewLoading(true)
    setViewDetail(null)
    try {
      const detail = await getOcrTool(workspaceId, toolId)
      setViewDetail(detail)
    } catch {
      void message.error(t('common.error'))
      setViewOpen(false)
    } finally {
      setViewLoading(false)
    }
  }

  const closeView = () => {
    setViewOpen(false)
    setViewDetail(null)
  }

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
      width: 160,
      ellipsis: true,
      render: (value: string | null) => resolveAuthLabel(value),
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
      width: 200,
      render: (_, row) => (
        <Space>
          <Button
            type="text"
            icon={<EyeOutlined />}
            onClick={() => void openView(row.id)}
            aria-label={t('settings.ocrToolsView')}
          />
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
        auth_type:
          detail.auth_type != null
            ? canonicalOcrAuthType(detail.auth_type) || detail.auth_type
            : undefined,
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
    const raw = values.auth_type ?? ''
    const authTypeStored = canonicalOcrAuthType(raw) || null
    return {
      name: values.name.trim(),
      url: values.url.trim(),
      auth_type: authTypeStored,
      user_name: isOcrBasicAuth(raw) ? values.user_name?.trim() || null : null,
      user_passwd: isOcrBasicAuth(raw) ? values.user_passwd?.trim() || null : null,
      api_key: isOcrApiKeyAuth(raw) ? values.api_key?.trim() || null : null,
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
        auth_type: legacy.apiKey.trim() ? OCR_AUTH_API_KEY : OCR_AUTH_NONE,
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

  const authType = watchedAuthType ?? ''
  const showBasicFields = isOcrBasicAuth(authType)
  const showApiKeyField = isOcrApiKeyAuth(authType)

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
          <Form.Item
            name="auth_type"
            label={t('settings.ocrToolsAuthType')}
            rules={[{ required: true, message: t('settings.ocrAuthTypeRequired') }]}
          >
            <Select
              loading={authDictLoading}
              options={authSelectOptions}
              optionFilterProp="label"
              showSearch
            />
          </Form.Item>
          {showBasicFields ? (
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
          {showApiKeyField ? (
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

      <Drawer
        title={t('settings.ocrToolsView')}
        width={560}
        open={viewOpen}
        onClose={closeView}
        destroyOnHidden
      >
        {viewLoading ? (
          <div style={{ padding: 24, textAlign: 'center' }}>
            <Spin />
          </div>
        ) : viewDetail ? (
          <div className="minerva-ocr-settings__drawer-detail">
            <Typography.Title level={5} style={{ marginTop: 0 }}>
              {t('settings.ocrDetailBaseSection')}
            </Typography.Title>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label={t('settings.ocrToolsName')}>
                {viewDetail.name}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.ocrToolsUrl')}>
                {viewDetail.url}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.ocrToolsAuthType')}>
                {resolveAuthLabel(viewDetail.auth_type)}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.ocrToolsRemark')}>
                {viewDetail.remark?.trim() ? viewDetail.remark : '—'}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.ocrDetailCreatedAt')}>
                {formatDateTime(viewDetail.create_at)}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.ocrDetailUpdatedAt')}>
                {formatDateTime(viewDetail.update_at)}
              </Descriptions.Item>
            </Descriptions>

            <Divider />
            <Typography.Title level={5}>{t('settings.ocrDetailCredentialSection')}</Typography.Title>

            {isOcrBasicAuth(viewDetail.auth_type) ? (
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label={t('settings.ocrToolsUsername')}>
                  {viewDetail.user_name?.trim() ? viewDetail.user_name : '—'}
                </Descriptions.Item>
                <Descriptions.Item label={t('settings.ocrToolsPassword')}>
                  {viewDetail.user_passwd ? (
                    <Input.Password readOnly value={viewDetail.user_passwd} />
                  ) : (
                    '—'
                  )}
                </Descriptions.Item>
              </Descriptions>
            ) : null}

            {isOcrApiKeyAuth(viewDetail.auth_type) ? (
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label={t('settings.ocrToolsApiKey')}>
                  {viewDetail.api_key ? (
                    <Input.Password readOnly value={viewDetail.api_key} />
                  ) : (
                    '—'
                  )}
                </Descriptions.Item>
              </Descriptions>
            ) : null}

            {isOcrNoneAuth(viewDetail.auth_type) ? (
              <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                {t('settings.ocrDetailNoneCredentials')}
              </Typography.Paragraph>
            ) : null}

            {!isOcrBasicAuth(viewDetail.auth_type) &&
            !isOcrApiKeyAuth(viewDetail.auth_type) &&
            !isOcrNoneAuth(viewDetail.auth_type) ? (
              <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                {t('settings.ocrDetailCustomAuthHint')}
              </Typography.Paragraph>
            ) : null}
          </div>
        ) : null}
      </Drawer>
    </div>
  )
}
