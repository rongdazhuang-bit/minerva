import { DeleteOutlined, EditOutlined, EyeOutlined, PlusOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Divider,
  Drawer,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Typography,
  message,
  type DescriptionsProps,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { listAllDicts, listDictItems, type SysDictItem } from '@/api/dicts'
import {
  createModelProvider,
  deleteModelProvider,
  getModelProvider,
  listModelProvidersGrouped,
  patchModelProvider,
  type ModelProviderCreateBody,
  type ModelProviderDetail,
  type ModelProviderGroup,
  type ModelProviderGroupItem,
} from '@/api/modelProviders'
import { useAuth } from '@/app/AuthContext'
import {
  OCR_AUTH_API_KEY,
  OCR_AUTH_BASIC,
  OCR_AUTH_NONE,
  canonicalOcrAuthType,
  isOcrApiKeyAuth,
  isOcrBasicAuth,
  isOcrNoneAuth,
} from '@/features/settings/ocr/ocrAuthType'
import './ModelProvidersPage.css'

const { Paragraph, Text } = Typography

const DICT_CODE_PROVIDER = 'MODEL_PROVIDER'
const DICT_CODE_MODEL_TYPE = 'MODEL_TYPE'
const DICT_CODE_AUTH = 'AUTH_TYPE'

type FormValues = {
  provider_name?: string
  model_name: string
  model_type: string
  enabled: boolean
  load_balancing_enabled: boolean
  auth_type?: string
  endpoint_url?: string
  auth_name?: string
  auth_passwd?: string
  api_key?: string
  context_size?: number | null
  max_tokens_to_sample?: number | null
  model_config?: string
}

function sortDictItems(items: SysDictItem[]) {
  return [...items].sort(
    (a, b) =>
      (b.item_sort ?? 0) - (a.item_sort ?? 0) || a.code.localeCompare(b.code),
  )
}

function stableModelSort(a: ModelProviderGroupItem, b: ModelProviderGroupItem) {
  return String(a.id).localeCompare(String(b.id))
}

/** 查看：能解析为 JSON 时做缩进展示，否则保持原文。 */
function formatModelConfigForView(raw: string): string {
  const s = raw.trim()
  if (!s) return ''
  try {
    return JSON.stringify(JSON.parse(s) as unknown, null, 2)
  } catch {
    return raw
  }
}

/** 表单/接口侧统一为 string | null，避免 onFinish 漏字段、或非字符串导致 .trim 异常 */
function normModelConfigField(v: unknown): string | null {
  if (v == null) return null
  const s = String(v).trim()
  return s === '' ? null : s
}

/** 查看抽屉内上下两段 Descriptions 共用，保证两表标签/内容列对齐 */
const viewDrawerDescriptionStyles: NonNullable<DescriptionsProps['styles']> = {
  label: { minWidth: 200, width: 200, maxWidth: 200, verticalAlign: 'top' },
  content: { wordBreak: 'break-all' as const, overflowWrap: 'anywhere' as const },
}

export function ModelProvidersPage() {
  const { t } = useTranslation()
  const { workspaceId, isWorkspaceManager, workspaceRole, isAuthenticated } = useAuth()
  const [form] = Form.useForm<FormValues>()

  const [groups, setGroups] = useState<ModelProviderGroup[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingBase, setEditingBase] = useState<ModelProviderDetail | null>(null)

  const [providerItems, setProviderItems] = useState<SysDictItem[]>([])
  const [typeItems, setTypeItems] = useState<SysDictItem[]>([])
  const [authItems, setAuthItems] = useState<SysDictItem[]>([])
  const [dictLoading, setDictLoading] = useState(false)

  const [viewOpen, setViewOpen] = useState(false)
  const [viewLoading, setViewLoading] = useState(false)
  const [viewDetail, setViewDetail] = useState<ModelProviderDetail | null>(null)

  const watchedAuthType = Form.useWatch('auth_type', form)

  const loadDicts = useCallback(async () => {
    if (!workspaceId) return
    setDictLoading(true)
    try {
      const dicts = await listAllDicts(workspaceId)
      const p = dicts.find((d) => d.dict_code === DICT_CODE_PROVIDER)
      const m = dicts.find((d) => d.dict_code === DICT_CODE_MODEL_TYPE)
      const a = dicts.find((d) => d.dict_code === DICT_CODE_AUTH)
      const [pRows, mRows, aRows] = await Promise.all([
        p ? listDictItems(workspaceId, p.id) : Promise.resolve([] as SysDictItem[]),
        m ? listDictItems(workspaceId, m.id) : Promise.resolve([] as SysDictItem[]),
        a ? listDictItems(workspaceId, a.id) : Promise.resolve([] as SysDictItem[]),
      ])
      setProviderItems(pRows)
      setTypeItems(mRows)
      setAuthItems(aRows)
    } catch {
      setProviderItems([])
      setTypeItems([])
      setAuthItems([])
    } finally {
      setDictLoading(false)
    }
  }, [workspaceId])

  useEffect(() => {
    void loadDicts()
  }, [loadDicts])

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
    if (m.size === 0) {
      m.set(OCR_AUTH_NONE, t('settings.ocrAuthTypeDictNone'))
      m.set(OCR_AUTH_BASIC, t('settings.ocrAuthTypeDictBasic'))
      m.set(OCR_AUTH_API_KEY, t('settings.ocrAuthTypeDictApiKey'))
    }
    m.set('none', t('settings.ocrAuthTypeDictNone'))
    m.set('basic', t('settings.ocrAuthTypeDictBasic'))
    m.set('api_key', t('settings.ocrAuthTypeDictApiKey'))
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
      const rows = await listModelProvidersGrouped(workspaceId)
      for (const g of rows) {
        g.items.sort(stableModelSort)
      }
      setGroups(rows)
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
      baseAuthSelectOptions.find((o) => o.value === OCR_AUTH_API_KEY) ??
      baseAuthSelectOptions[0]
    form.setFieldsValue({ auth_type: next?.value })
  }, [open, editingId, baseAuthSelectOptions, form])

  const providerOptions = useMemo(() => {
    const sorted = sortDictItems(providerItems)
    if (sorted.length === 0) {
      return []
    }
    return sorted.map((i) => ({ value: i.name, label: `${i.name} (${i.code})` }))
  }, [providerItems])

  const modelTypeOptions = useMemo(() => {
    const sorted = sortDictItems(typeItems)
    if (sorted.length === 0) {
      return []
    }
    return sorted.map((i) => ({ value: i.name, label: `${i.name} (${i.code})` }))
  }, [typeItems])

  const resolveAuthLabel = (code: string) => {
    const exact = authLabelByCode.get(code)
    if (exact) return exact
    const canon = canonicalOcrAuthType(code)
    return authLabelByCode.get(canon) ?? code
  }

  const formatDateTime = (v: string | null | undefined) =>
    v ? new Date(v).toLocaleString(undefined, { hour12: false }) : '—'

  const buildPayload = (values: FormValues): ModelProviderCreateBody => {
    const raw = values.auth_type ?? ''
    return {
      provider_name: (values.provider_name ?? '').trim(),
      model_name: values.model_name.trim(),
      model_type: (values.model_type ?? '').trim(),
      enabled: Boolean(values.enabled),
      load_balancing_enabled: Boolean(values.load_balancing_enabled),
      auth_type: canonicalOcrAuthType(raw) || raw.trim(),
      endpoint_url: values.endpoint_url?.trim() ? values.endpoint_url.trim() : null,
      auth_name: isOcrBasicAuth(raw) ? values.auth_name?.trim() || null : null,
      auth_passwd: isOcrBasicAuth(raw) ? values.auth_passwd?.trim() || null : null,
      api_key: isOcrApiKeyAuth(raw) ? values.api_key?.trim() || null : null,
      context_size: values.context_size ?? null,
      max_tokens_to_sample: values.max_tokens_to_sample ?? null,
      model_config: normModelConfigField(values.model_config),
    }
  }

  const isSecretUnchanged = (next: string | null | undefined, prev: string | null | undefined) => {
    const a = (next ?? '').trim()
    if (a !== '') return false
    return Boolean((prev ?? '').trim())
  }

  const openCreate = (providerName?: string) => {
    setEditingId(null)
    setEditingBase(null)
    form.resetFields()
    form.setFieldsValue({
      provider_name: providerName,
      model_name: '',
      model_type: modelTypeOptions[0]?.value,
      enabled: true,
      load_balancing_enabled: false,
      model_config: '',
    })
    setOpen(true)
  }

  const openEdit = async (modelId: string) => {
    if (!workspaceId) return
    setEditingId(modelId)
    setSubmitting(true)
    try {
      const detail = await getModelProvider(workspaceId, modelId)
      setEditingBase(detail)
      const rawAuth = detail.auth_type
      const authType =
        rawAuth != null ? canonicalOcrAuthType(rawAuth) || rawAuth : undefined
      form.setFieldsValue({
        provider_name: detail.provider_name,
        model_name: detail.model_name,
        model_type: detail.model_type,
        enabled: detail.enabled,
        load_balancing_enabled: detail.load_balancing_enabled,
        auth_type: authType,
        endpoint_url: detail.endpoint_url ?? '',
        auth_name: detail.auth_name ?? '',
        auth_passwd: '',
        api_key: '',
        context_size: detail.context_size ?? null,
        max_tokens_to_sample: detail.max_tokens_to_sample ?? null,
        model_config: normModelConfigField(detail.model_config) ?? '',
      })
      setOpen(true)
    } catch {
      void message.error(t('common.error'))
    } finally {
      setSubmitting(false)
    }
  }

  const openView = async (modelId: string) => {
    if (!workspaceId) return
    setViewOpen(true)
    setViewLoading(true)
    setViewDetail(null)
    try {
      const d = await getModelProvider(workspaceId, modelId)
      setViewDetail(d)
    } catch {
      void message.error(t('common.error'))
      setViewOpen(false)
    } finally {
      setViewLoading(false)
    }
  }

  const handleDelete = async (modelId: string) => {
    if (!workspaceId) return
    try {
      await deleteModelProvider(workspaceId, modelId)
      void message.success(t('settings.modelProvidersDeleted'))
      await load()
    } catch {
      void message.error(t('common.error'))
    }
  }

  const onSubmit = async (values: FormValues) => {
    if (!workspaceId) return
    if (!isWorkspaceManager) {
      void message.error(t('settings.modelProvidersReadOnly'))
      return
    }
    setSubmitting(true)
    try {
      // onFinish 可能省略未参与校验的表单项；以 getFieldsValue 为底、values 覆盖
      const merged: FormValues = { ...(form.getFieldsValue() as FormValues), ...values }
      if (editingId) {
        if (!editingBase) {
          void message.error(t('common.error'))
          return
        }
        const next = buildPayload(merged)
        const patch: Record<string, unknown> = {}
        const keys: (keyof ModelProviderCreateBody)[] = [
          'provider_name',
          'model_name',
          'model_type',
          'enabled',
          'load_balancing_enabled',
          'auth_type',
          'endpoint_url',
          'auth_name',
          'context_size',
          'max_tokens_to_sample',
        ]
        for (const k of keys) {
          if (next[k] !== (editingBase as unknown as Record<string, unknown>)[k]) {
            patch[k] = next[k]
          }
        }
        if (normModelConfigField(next.model_config) !== normModelConfigField(editingBase.model_config)) {
          patch.model_config = next.model_config
        }
        if (!isSecretUnchanged(next.api_key, editingBase.api_key) && isOcrApiKeyAuth(merged.auth_type ?? '')) {
          patch.api_key = next.api_key
        }
        if (!isSecretUnchanged(next.auth_passwd, editingBase.auth_passwd) && isOcrBasicAuth(merged.auth_type ?? '')) {
          patch.auth_passwd = next.auth_passwd
        }
        await patchModelProvider(workspaceId, editingId, patch)
        void message.success(t('settings.modelProvidersUpdated'))
      } else {
        await createModelProvider(workspaceId, buildPayload(merged))
        void message.success(t('settings.modelProvidersCreated'))
      }
      setOpen(false)
      await load()
    } catch {
      void message.error(t('common.error'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggleEnabled = async (row: ModelProviderGroupItem, next: boolean) => {
    if (!workspaceId || !isWorkspaceManager) return
    const prev = row.enabled
    setGroups((g0) =>
      g0.map((g) => ({
        ...g,
        items: g.items.map((it) => (it.id === row.id ? { ...it, enabled: next } : it)),
      })),
    )
    try {
      await patchModelProvider(workspaceId, row.id, { enabled: next })
    } catch {
      void message.error(t('common.error'))
      setGroups((g0) =>
        g0.map((g) => ({
          ...g,
          items: g.items.map((it) => (it.id === row.id ? { ...it, enabled: prev } : it)),
        })),
      )
    }
  }

  const handleToggleLoadBalancing = async (row: ModelProviderGroupItem, next: boolean) => {
    if (!workspaceId || !isWorkspaceManager) return
    const prev = row.load_balancing_enabled
    setGroups((g0) =>
      g0.map((g) => ({
        ...g,
        items: g.items.map((it) =>
          it.id === row.id ? { ...it, load_balancing_enabled: next } : it,
        ),
      })),
    )
    try {
      await patchModelProvider(workspaceId, row.id, { load_balancing_enabled: next })
    } catch {
      void message.error(t('common.error'))
      setGroups((g0) =>
        g0.map((g) => ({
          ...g,
          items: g.items.map((it) =>
            it.id === row.id ? { ...it, load_balancing_enabled: prev } : it,
          ),
        })),
      )
    }
  }

  const authTypeForRow = watchedAuthType ?? ''
  const showBasic = isOcrBasicAuth(authTypeForRow)
  const showApiKey = isOcrApiKeyAuth(authTypeForRow)
  const isNone = isOcrNoneAuth(authTypeForRow)

  /** Horizontal scroll width; model name column uses ~20% of this value. */
  const tableScrollX = 1400

  const columns: ColumnsType<ModelProviderGroupItem> = [
    {
      title: t('settings.modelProvidersColModel'),
      dataIndex: 'model_name',
      key: 'model_name',
      width: Math.round(tableScrollX * 0.2),
      ellipsis: true,
    },
    { title: t('settings.modelProvidersColType'), dataIndex: 'model_type', key: 'model_type', width: 140 },
    {
      title: t('settings.modelProvidersColEndpoint'),
      dataIndex: 'endpoint_url',
      key: 'endpoint_url',
      ellipsis: { showTitle: true },
      minWidth: 400,
      render: (v) => (v ? String(v) : '—'),
    },
    {
      title: t('settings.modelProvidersColAuth'),
      dataIndex: 'auth_type',
      key: 'auth_type',
      width: 140,
      render: (v) => resolveAuthLabel(String(v)),
    },
    {
      title: t('settings.modelProvidersColEnabled'),
      dataIndex: 'enabled',
      key: 'enabled',
      width: 90,
      render: (v, row) => (
        <Switch
          checked={Boolean(v)}
          disabled={!isWorkspaceManager}
          onChange={(n) => void handleToggleEnabled(row, n)}
        />
      ),
    },
    {
      title: t('settings.modelProvidersColLb'),
      dataIndex: 'load_balancing_enabled',
      key: 'load_balancing_enabled',
      width: 100,
      render: (v, row) => (
        <Switch
          checked={Boolean(v)}
          disabled={!isWorkspaceManager}
          onChange={(n) => void handleToggleLoadBalancing(row, n)}
        />
      ),
    },
    {
      title: t('settings.modelProvidersColCreatedAt'),
      dataIndex: 'create_at',
      key: 'create_at',
      width: 180,
      render: (v) => formatDateTime(String(v)),
    },
    {
      title: t('settings.modelProvidersColActions'),
      key: 'actions',
      width: 200,
      render: (_, row) => (
        <Space>
          <Button
            type="text"
            icon={<EyeOutlined />}
            onClick={() => void openView(row.id)}
            aria-label={t('settings.modelProvidersView')}
          />
          {isWorkspaceManager ? (
            <>
              <Button
                type="text"
                icon={<EditOutlined />}
                onClick={() => void openEdit(row.id)}
                aria-label={t('settings.modelProvidersEdit')}
              />
              <Popconfirm title={t('settings.modelProvidersDeleteConfirm')} onConfirm={() => void handleDelete(row.id)}>
                <Button type="text" danger icon={<DeleteOutlined />} aria-label={t('settings.modelProvidersDelete')} />
              </Popconfirm>
            </>
          ) : null}
        </Space>
      ),
    },
  ]

  if (!workspaceId) {
    return (
      <div className="minerva-model-providers">
        <Paragraph>{t('settings.ocrNoWorkspace')}</Paragraph>
      </div>
    )
  }

  return (
    <div className="minerva-model-providers">
      {isAuthenticated && !workspaceRole ? (
        <Alert
          className="minerva-model-providers__ro"
          type="warning"
          showIcon
          message={t('settings.modelProvidersTokenMissingRole')}
        />
      ) : null}
      {isWorkspaceManager ? null : (
        <Alert className="minerva-model-providers__ro" type="info" showIcon message={t('settings.modelProvidersReadOnlyHint')} />
      )}

      <Card size="small" variant="borderless" className="minerva-model-providers__card">
        <div className="minerva-model-providers__toolbar">
          {isWorkspaceManager ? (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => openCreate()} disabled={dictLoading && providerOptions.length === 0}>
              {t('settings.modelProvidersAdd')}
            </Button>
          ) : null}
        </div>

        <div className="minerva-model-providers__body minerva-scrollbar-styled">
          <SpinWrapper loading={loading || dictLoading}>
            {groups.length === 0 ? (
              <div className="minerva-model-providers__table-wrap">
                <Table<ModelProviderGroupItem>
                  size="small"
                  className="minerva-model-providers__table"
                  rowKey="id"
                  pagination={false}
                  columns={columns}
                  dataSource={[]}
                  scroll={{ x: tableScrollX }}
                  locale={{ emptyText: t('settings.modelProvidersEmpty') }}
                />
              </div>
            ) : (
              <Collapse
                className="minerva-model-providers__collapse"
                defaultActiveKey={groups.map((g) => g.provider_name)}
                items={groups.map((g) => ({
                  key: g.provider_name,
                  label: (
                    <div className="minerva-model-providers__group-title">
                      <Text strong style={{ color: 'var(--minerva-ink, #e8f0f8)' }}>
                        {g.provider_name}
                      </Text>
                      <Text type="secondary" className="minerva-model-providers__group-count">
                        {t('settings.modelProvidersGroupCount', { count: g.items.length })}
                      </Text>
                    </div>
                  ),
                  children: (
                    <div className="minerva-model-providers__table-wrap">
                      <Table<ModelProviderGroupItem>
                        size="small"
                        className="minerva-model-providers__table"
                        rowKey="id"
                        pagination={false}
                        columns={columns}
                        dataSource={g.items}
                        scroll={{ x: tableScrollX }}
                        locale={{ emptyText: t('settings.modelProvidersEmpty') }}
                        footer={
                          isWorkspaceManager
                            ? () => (
                                <div className="minerva-model-providers__group-footer">
                                  <Button
                                    size="small"
                                    icon={<PlusOutlined />}
                                    onClick={() => openCreate(g.provider_name)}
                                    disabled={dictLoading && providerOptions.length === 0}
                                  >
                                    {t('settings.modelProvidersAddInGroup')}
                                  </Button>
                                </div>
                              )
                            : undefined
                        }
                      />
                    </div>
                  ),
                }))}
              />
            )}
          </SpinWrapper>
        </div>
      </Card>

      <Drawer
        title={editingId ? t('settings.modelProvidersEdit') : t('settings.modelProvidersAdd')}
        width={640}
        placement="right"
        open={open}
        onClose={() => setOpen(false)}
        destroyOnClose
        classNames={{ body: 'minerva-scrollbar-styled' }}
        extra={
          <Space>
            <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
            <Button type="primary" htmlType="submit" loading={submitting} onClick={() => void form.submit()}>
              {t('common.save')}
            </Button>
          </Space>
        }
      >
        <Form<FormValues> form={form} layout="vertical" onFinish={onSubmit}>
          <Form.Item
            name="provider_name"
            label={t('settings.modelProvidersFieldProvider')}
            rules={[{ required: true, message: t('settings.modelProvidersFieldProviderRequired') }]}
          >
            <Select
              showSearch
              allowClear
              optionFilterProp="label"
              disabled={dictLoading && providerOptions.length === 0}
              options={providerOptions}
              placeholder={t('settings.modelProvidersFieldProviderPh')}
            />
          </Form.Item>
          <Form.Item
            name="model_name"
            label={t('settings.modelProvidersFieldModelName')}
            rules={[{ required: true, message: t('settings.modelProvidersFieldModelNameRequired') }]}
          >
            <Input allowClear autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="model_type"
            label={t('settings.modelProvidersFieldModelType')}
            rules={[{ required: true, message: t('settings.modelProvidersFieldModelTypeRequired') }]}
          >
            <Select
              showSearch
              allowClear
              optionFilterProp="label"
              disabled={dictLoading && modelTypeOptions.length === 0}
              options={modelTypeOptions}
              placeholder={t('settings.modelProvidersFieldModelTypePh')}
            />
          </Form.Item>
          <Form.Item name="enabled" label={t('settings.modelProvidersFieldEnabled')} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            name="load_balancing_enabled"
            label={t('settings.modelProvidersFieldLb')}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
          <Form.Item
            name="auth_type"
            label={t('settings.ocrToolsAuthType')}
            rules={[{ required: true, message: t('settings.ocrAuthTypeRequired') }]}
          >
            <Select
              showSearch
              allowClear
              options={authSelectOptions}
              optionFilterProp="label"
            />
          </Form.Item>
          <Form.Item name="endpoint_url" label={t('settings.ocrToolsUrl')}>
            <Input allowClear autoComplete="off" placeholder="https://..." />
          </Form.Item>
          {showBasic ? (
            <>
              <Form.Item
                name="auth_name"
                label={t('settings.ocrToolsUsername')}
                rules={[{ required: true, message: t('settings.ocrToolsUsernameRequired') }]}
              >
                <Input allowClear autoComplete="off" />
              </Form.Item>
              <Form.Item
                name="auth_passwd"
                label={t('settings.ocrToolsPassword')}
                rules={[
                  {
                    required: !editingId,
                    message: t('settings.ocrToolsPasswordRequired'),
                  },
                ]}
                extra={editingId ? t('settings.modelProvidersSecretKeepHint') : undefined}
              >
                <Input.Password
                  allowClear
                  autoComplete="new-password"
                  placeholder={editingId ? t('settings.modelProvidersPasswordPlaceholder') : undefined}
                />
              </Form.Item>
            </>
          ) : null}
          {showApiKey ? (
            <Form.Item
              name="api_key"
              label={t('settings.ocrToolsApiKey')}
              rules={[{ required: !editingId, message: t('settings.ocrToolsApiKeyRequired') }]}
              extra={editingId ? t('settings.modelProvidersSecretKeepHint') : undefined}
            >
              <Input.Password
                allowClear
                autoComplete="new-password"
                placeholder={editingId ? t('settings.modelProvidersApiKeyPlaceholder') : undefined}
              />
            </Form.Item>
          ) : null}
          {isNone ? (
            <Alert type="info" showIcon message={t('settings.modelProvidersNoneAuthHint')} className="minerva-model-providers__form-alert" />
          ) : null}
          <Form.Item name="context_size" label={t('settings.modelProvidersFieldContext')}>
            <InputNumber className="minerva-model-providers__num" min={1} max={32767} />
          </Form.Item>
          <Form.Item name="max_tokens_to_sample" label={t('settings.modelProvidersFieldMaxTokens')}>
            <InputNumber className="minerva-model-providers__num" min={1} max={32767} />
          </Form.Item>
          <Form.Item name="model_config" label={t('settings.modelProvidersFieldConfig')}>
            <Input.TextArea
              allowClear
              autoSize={{ minRows: 3, maxRows: 10 }}
              placeholder={t('settings.modelProvidersFieldConfigPh')}
            />
          </Form.Item>
        </Form>
      </Drawer>

      <Drawer
        title={t('settings.modelProvidersView')}
        width={640}
        placement="right"
        open={viewOpen}
        onClose={() => setViewOpen(false)}
        destroyOnClose
        classNames={{ body: 'minerva-scrollbar-styled' }}
      >
        {viewLoading || !viewDetail ? (
          <Paragraph>{t('common.loading')}</Paragraph>
        ) : (
          <div className="minerva-model-providers__view">
            <Descriptions column={1} size="small" bordered styles={viewDrawerDescriptionStyles}>
              <Descriptions.Item label={t('settings.modelProvidersFieldProvider')}>
                {viewDetail.provider_name}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.modelProvidersFieldModelName')}>{viewDetail.model_name}</Descriptions.Item>
              <Descriptions.Item label={t('settings.modelProvidersFieldModelType')}>{viewDetail.model_type}</Descriptions.Item>
              <Descriptions.Item label={t('settings.modelProvidersFieldEnabled')}>
                {viewDetail.enabled ? t('common.yes') : t('common.no')}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.modelProvidersFieldLb')}>
                {viewDetail.load_balancing_enabled ? t('common.yes') : t('common.no')}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.ocrToolsAuthType')}>
                {resolveAuthLabel(String(viewDetail.auth_type))}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.ocrToolsUrl')}>
                {viewDetail.endpoint_url ? (
                  <Typography.Text copyable={{ onCopy: () => void message.success(t('common.copied')) }} style={{ wordBreak: 'break-all' }}>
                    {viewDetail.endpoint_url}
                  </Typography.Text>
                ) : (
                  '—'
                )}
              </Descriptions.Item>
            </Descriptions>
            <Divider />
            <Typography.Text strong>{t('settings.ocrDetailCredentialSection')}</Typography.Text>
            <Descriptions
              style={{ marginTop: 10 }}
              column={1}
              size="small"
              bordered
              styles={viewDrawerDescriptionStyles}
            >
              <Descriptions.Item label={t('settings.ocrToolsUsername')}>
                {viewDetail.auth_name ? (
                  <Typography.Text copyable={{ onCopy: () => void message.success(t('common.copied')) }}>{viewDetail.auth_name}</Typography.Text>
                ) : (
                  '—'
                )}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.ocrToolsPassword')}>
                {viewDetail.auth_passwd ? (
                  <Typography.Text
                    copyable={{ onCopy: () => void message.success(t('common.copied')) }}
                    style={{ wordBreak: 'break-all' }}
                  >
                    {viewDetail.auth_passwd}
                  </Typography.Text>
                ) : (
                  '—'
                )}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.ocrToolsApiKey')}>
                {viewDetail.api_key ? (
                  <Typography.Text
                    copyable={{ onCopy: () => void message.success(t('common.copied')) }}
                    style={{ wordBreak: 'break-all' }}
                  >
                    {viewDetail.api_key}
                  </Typography.Text>
                ) : (
                  '—'
                )}
              </Descriptions.Item>
            </Descriptions>
            <Divider />
            <Typography.Text type="secondary">
              {t('settings.ocrDetailCreatedAt')}: {formatDateTime(viewDetail.create_at)} · {t('settings.ocrDetailUpdatedAt')}:{' '}
              {formatDateTime(viewDetail.update_at)}
            </Typography.Text>
            {viewDetail.model_config ? (
              <>
                <Divider />
                <div className="minerva-model-providers__view-config-head">
                  <Text strong>{t('settings.modelProvidersFieldConfig')}</Text>
                  <Text type="secondary" className="minerva-model-providers__view-config-hint">
                    {t('settings.modelProvidersViewConfigDbHint')}
                  </Text>
                </div>
                <pre className="minerva-model-providers__pre minerva-model-providers__pre--json">
                  {formatModelConfigForView(viewDetail.model_config)}
                </pre>
              </>
            ) : null}
          </div>
        )}
      </Drawer>
    </div>
  )
}

function SpinWrapper(props: { loading: boolean; children: ReactNode }) {
  return <Spin spinning={props.loading}>{props.children}</Spin>
}
