import { DeleteOutlined, EditOutlined, EyeOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons'
import {
  Button,
  Card,
  Descriptions,
  Divider,
  Drawer,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SysDictItem } from '@/api/dicts'
import { useDictItemTree } from '@/hooks/useDictItemTree'
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
  MineruOcrParamsFields,
  OcrToolParamsTabs,
  PaddleOcrParamsFields,
} from './PaddleOcrParamsTab'
import {
  MINERU_OCR_TYPE_CODE,
  defaultMineruFormValues,
  mineruFormValuesToOcrConfig,
  ocrConfigToMineruFormValues,
} from './mineruParams'
import {
  defaultPaddleFormValues,
  ocrConfigToPaddleFormValues,
  paddleFormValuesToOcrConfig,
  PADDLE_OCR_TYPE_CODE,
} from './paddleOcrParams'
import {
  OCR_AUTH_API_KEY,
  OCR_AUTH_BASIC,
  OCR_AUTH_NONE,
  canonicalOcrAuthType,
  isOcrApiKeyAuth,
  isOcrBasicAuth,
  isOcrNoneAuth,
} from './ocrAuthType'
import { clearOcrSettings, readOcrSettings } from './ocrSettingsStorage'
import './OcrSettingsPage.css'

const { Paragraph } = Typography

/** 数据字典中 OCR 认证方式的字典编码（与「数据字典」菜单中的 dict_code 一致）。 */
const AUTH_TYPE_DICT_CODE = 'AUTH_TYPE'

/** OCR 引擎类型（如 Paddle），字典编码 TOOL_OCR。 */
const OCR_TYPE_DICT_CODE = 'TOOL_OCR'

type OcrFormValues = {
  name: string
  url: string
  auth_type?: string
  user_name?: string
  user_passwd?: string
  api_key?: string
  remark?: string
  ocr_type?: string
  /** Nested Paddle option inputs; serialized into `ocr_config` when type is PADDLE_OCR. */
  paddle?: Record<string, unknown>
  /** MinerU option inputs; serialized into `ocr_config` when type is MINERU. */
  mineru?: Record<string, unknown>
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
  const authDictQ = useDictItemTree(AUTH_TYPE_DICT_CODE)
  const authItems = useMemo(() => authDictQ.data?.flat ?? [], [authDictQ.data])
  const authDictLoading = authDictQ.isLoading
  const ocrTypeDictQ = useDictItemTree(OCR_TYPE_DICT_CODE)
  const ocrTypeItems = useMemo(() => ocrTypeDictQ.data?.flat ?? [], [ocrTypeDictQ.data])
  const ocrTypeDictLoading = ocrTypeDictQ.isLoading
  const [viewOpen, setViewOpen] = useState(false)
  const [viewLoading, setViewLoading] = useState(false)
  const [viewDetail, setViewDetail] = useState<OcrToolDetail | null>(null)

  const watchedAuthType = Form.useWatch('auth_type', form)
  const watchedOcrType = Form.useWatch('ocr_type', form) as string | undefined
  const legacy = useMemo(() => readOcrSettings(), [])
  const canImportLegacy = legacy.mode === 'http' && legacy.baseUrl.trim().length > 0

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

  const ocrTypeLabelByCode = useMemo(() => {
    const m = new Map<string, string>()
    for (const i of sortDictItems(ocrTypeItems)) {
      m.set(i.code, i.name)
    }
    return m
  }, [ocrTypeItems])

  const ocrTypeSelectOptions = useMemo(() => {
    const sorted = sortDictItems(ocrTypeItems)
    if (sorted.length > 0) {
      return sorted.map((i) => ({ value: i.code, label: i.name }))
    }
    return [{ value: PADDLE_OCR_TYPE_CODE, label: t('settings.ocrToolsOcrTypePaddleFallback') }]
  }, [ocrTypeItems, t])

  const resolveOcrTypeLabel = (code: string | null | undefined) => {
    if (code == null || code === '') return '—'
    return ocrTypeLabelByCode.get(code) ?? code
  }

  const authSelectOptions = useMemo(() => {
    if (!open) return baseAuthSelectOptions
    const cur = watchedAuthType
    if (cur != null && cur !== '' && !baseAuthSelectOptions.some((o) => o.value === cur)) {
      return [...baseAuthSelectOptions, { value: cur, label: cur }]
    }
    return baseAuthSelectOptions
  }, [baseAuthSelectOptions, open, watchedAuthType])

  const ocrTypeSelectOptionsWithCurrent = useMemo(() => {
    if (!open) return ocrTypeSelectOptions
    const cur = watchedOcrType
    if (cur != null && cur !== '' && !ocrTypeSelectOptions.some((o) => o.value === cur)) {
      return [...ocrTypeSelectOptions, { value: cur, label: cur }]
    }
    return ocrTypeSelectOptions
  }, [ocrTypeSelectOptions, open, watchedOcrType])

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

  const renderCopyablePlain = (value: string | null | undefined) => {
    const v = value?.trim()
    if (!v) return '—'
    return (
      <Typography.Text
        copyable={{
          onCopy: () => void message.success(t('common.copied')),
        }}
        style={{ wordBreak: 'break-all' }}
      >
        {v}
      </Typography.Text>
    )
  }

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
      title: t('settings.ocrToolsOcrType'),
      dataIndex: 'ocr_type',
      key: 'ocr_type',
      width: 140,
      ellipsis: true,
      render: (value: string | null) => resolveOcrTypeLabel(value),
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
    form.setFieldsValue({
      ocr_type: PADDLE_OCR_TYPE_CODE,
      paddle: defaultPaddleFormValues(),
      mineru: defaultMineruFormValues(),
    })
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
        ocr_type: detail.ocr_type?.trim() || PADDLE_OCR_TYPE_CODE,
        paddle: ocrConfigToPaddleFormValues(detail.ocr_config ?? undefined),
        mineru: ocrConfigToMineruFormValues(detail.ocr_config ?? undefined),
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
    const ocrType = values.ocr_type?.trim() || null
    let ocr_config: Record<string, unknown> | null = null
    if (ocrType === PADDLE_OCR_TYPE_CODE) {
      ocr_config = paddleFormValuesToOcrConfig(values.paddle) ?? null
    } else if (ocrType === MINERU_OCR_TYPE_CODE) {
      ocr_config = mineruFormValuesToOcrConfig(values.mineru) ?? null
    }
    return {
      name: values.name.trim(),
      url: values.url.trim(),
      auth_type: authTypeStored,
      user_name: isOcrBasicAuth(raw) ? values.user_name?.trim() || null : null,
      user_passwd: isOcrBasicAuth(raw) ? values.user_passwd?.trim() || null : null,
      api_key: isOcrApiKeyAuth(raw) ? values.api_key?.trim() || null : null,
      remark: values.remark?.trim() || null,
      ocr_type: ocrType,
      ocr_config,
    }
  }

  const onSubmit = async (values: OcrFormValues) => {
    if (!workspaceId) return
    let payload: OcrToolCreateBody
    try {
      payload = buildPayload(values)
    } catch (e) {
      if (e instanceof Error && e.message.startsWith('invalid_json:')) {
        const field = e.message.slice('invalid_json:'.length)
        void message.error(t('settings.ocrPaddleInvalidJson', { field }))
        return
      }
      throw e
    }
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
        ocr_type: PADDLE_OCR_TYPE_CODE,
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
            className="minerva-card-table-scroll-ocr minerva-ocr-settings__table"
            scroll={{ x: true, y: 'calc(100dvh - 320px)' }}
            sticky
          />
        </div>
      </Card>

      <Drawer
        title={editingId ? t('settings.ocrToolsEdit') : t('settings.ocrToolsAdd')}
        width={920}
        placement="right"
        open={open}
        onClose={() => setOpen(false)}
        destroyOnClose
        classNames={{ body: 'minerva-scrollbar-styled' }}
        extra={
          <Space>
            <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
            <Button type="primary" loading={submitting} onClick={() => void form.submit()}>
              {t('common.save')}
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical" onFinish={(values) => void onSubmit(values)}>
          <Form.Item
            name="ocr_type"
            label={t('settings.ocrToolsOcrType')}
            rules={[{ required: true, message: t('settings.ocrToolsOcrTypeRequired') }]}
          >
            <Select
              loading={ocrTypeDictLoading}
              options={ocrTypeSelectOptionsWithCurrent}
              optionFilterProp="label"
              showSearch
            />
          </Form.Item>
          <Form.Item
            name="name"
            label={t('settings.ocrToolsName')}
            rules={[{ required: true, message: t('settings.ocrToolsNameRequired') }]}
          >
            <Input allowClear maxLength={128} />
          </Form.Item>
          <Form.Item
            name="url"
            label={t('settings.ocrToolsUrl')}
            rules={[
              { required: true, message: t('settings.ocrErrorUrl') },
              { type: 'url', message: t('settings.ocrErrorUrl') },
            ]}
          >
            <Input allowClear maxLength={128} />
          </Form.Item>
          <Form.Item
            name="auth_type"
            label={t('settings.ocrToolsAuthType')}
            rules={[{ required: true, message: t('settings.ocrAuthTypeRequired') }]}
          >
            <Select
              allowClear
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
                <Input allowClear maxLength={64} />
              </Form.Item>
              <Form.Item
                name="user_passwd"
                label={t('settings.ocrToolsPassword')}
                rules={[{ required: true, message: t('settings.ocrToolsPasswordRequired') }]}
              >
                <Input.Password allowClear maxLength={128} />
              </Form.Item>
            </>
          ) : null}
          {showApiKeyField ? (
            <Form.Item
              name="api_key"
              label={t('settings.ocrToolsApiKey')}
              rules={[{ required: true, message: t('settings.ocrToolsApiKeyRequired') }]}
            >
              <Input.Password allowClear maxLength={128} />
            </Form.Item>
          ) : null}
          <Form.Item name="remark" label={t('settings.ocrToolsRemark')}>
            <Input allowClear maxLength={128} />
          </Form.Item>
          <OcrToolParamsTabs ocrType={watchedOcrType} t={t} />
        </Form>
      </Drawer>

      <Drawer
        title={t('settings.ocrToolsView')}
        width={920}
        placement="right"
        open={viewOpen}
        onClose={closeView}
        destroyOnClose
        classNames={{ body: 'minerva-scrollbar-styled' }}
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
              <Descriptions.Item label={t('settings.ocrToolsOcrType')}>
                {resolveOcrTypeLabel(viewDetail.ocr_type)}
              </Descriptions.Item>
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
                  {renderCopyablePlain(viewDetail.user_name)}
                </Descriptions.Item>
                <Descriptions.Item label={t('settings.ocrToolsPassword')}>
                  {renderCopyablePlain(viewDetail.user_passwd)}
                </Descriptions.Item>
              </Descriptions>
            ) : null}

            {isOcrApiKeyAuth(viewDetail.auth_type) ? (
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label={t('settings.ocrToolsApiKey')}>
                  {renderCopyablePlain(viewDetail.api_key)}
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

            <Divider />
            <Tabs
              items={[
                {
                  key: 'params',
                  label: t('settings.ocrParamsTab'),
                  children:
                    viewDetail.ocr_type === PADDLE_OCR_TYPE_CODE ? (
                      <Form
                        layout="vertical"
                        disabled
                        style={{ marginBottom: 0 }}
                        initialValues={{
                          paddle: ocrConfigToPaddleFormValues(viewDetail.ocr_config ?? undefined),
                        }}
                      >
                        <PaddleOcrParamsFields t={t} />
                      </Form>
                    ) : viewDetail.ocr_type === MINERU_OCR_TYPE_CODE ? (
                      <Form
                        layout="vertical"
                        disabled
                        style={{ marginBottom: 0 }}
                        initialValues={{
                          mineru: ocrConfigToMineruFormValues(viewDetail.ocr_config ?? undefined),
                        }}
                      >
                        <MineruOcrParamsFields t={t} />
                      </Form>
                    ) : viewDetail.ocr_config &&
                      typeof viewDetail.ocr_config === 'object' &&
                      Object.keys(viewDetail.ocr_config).length > 0 ? (
                      <Typography.Paragraph copyable style={{ marginBottom: 0 }}>
                        <pre
                          className="minerva-ocr-settings__json-view"
                          style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                        >
                          {JSON.stringify(viewDetail.ocr_config, null, 2)}
                        </pre>
                      </Typography.Paragraph>
                    ) : (
                      <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                        {t('settings.ocrParamsEmpty')}
                      </Typography.Paragraph>
                    ),
                },
              ]}
            />
          </div>
        ) : null}
      </Drawer>
    </div>
  )
}
