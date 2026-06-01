import { DeleteOutlined, EditOutlined, EyeOutlined, PlusOutlined } from '@ant-design/icons'
import {
  Button,
  Card,
  Descriptions,
  Drawer,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SysDictItem } from '@/api/dicts'
import {
  createFileStorage,
  deleteFileStorage,
  getFileStorage,
  listFileStorages,
  patchFileStorage,
  type FileStorageCreateBody,
  type FileStorageDetail,
  type FileStorageListItem,
} from '@/api/fileStorage'
import { useAuth } from '@/app/AuthContext'
import { showAppError, useAppMessage } from '@/app/useAppMessage'
import type { MessageInstance } from 'antd/es/message/interface'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import { useDictItemTree } from '@/hooks/useDictItemTree'
import './FileStoragePage.css'

const { Paragraph } = Typography
const STORAGE_TYPE_DICT_CODE = 'STORGE_TYPE'

/** Legacy or alternate auth_type tokens from API/DB, keyed by lower-case. */
const FILE_STORAGE_AUTH_ALIASES: Record<string, 'NONE' | 'BASIC' | 'API_KEY'> = {
  none: 'NONE',
  basic: 'BASIC',
  api_key: 'API_KEY',
}

/**
 * Normalize auth_type to the canonical values used by form Select options.
 * @param code Raw auth_type from API or database.
 * @returns Canonical NONE | BASIC | API_KEY when recognized; otherwise trimmed original.
 */
function canonicalFileStorageAuthType(code: string | null | undefined): string {
  if (code == null || code === '') return 'NONE'
  const trimmed = code.trim()
  const mapped = FILE_STORAGE_AUTH_ALIASES[trimmed.toLowerCase()]
  if (mapped) return mapped
  const upper = trimmed.toUpperCase()
  if (upper === 'NONE' || upper === 'BASIC' || upper === 'API_KEY') return upper
  return trimmed
}

/** Form values used by create/edit file storage drawer. */
type FileStorageFormValues = {
  name?: string
  bucket_name?: string
  type?: string
  enabled: boolean
  auth_type: string
  endpoint_url?: string
  api_key?: string
  secret_key?: string
  auth_name?: string
  auth_passwd?: string
}

/** Sort dictionary items by sort desc, then code asc. */
function sortDictItems(items: SysDictItem[]) {
  return [...items].sort(
    (a, b) =>
      (b.item_sort ?? 0) - (a.item_sort ?? 0) || a.code.localeCompare(b.code),
  )
}

/** Render copyable text for non-empty plain values. */
function renderCopyable(
  value: string | null | undefined,
  t: (key: string) => string,
  messageApi: MessageInstance,
) {
  const v = value?.trim()
  if (!v) return '—'
  return (
    <Typography.Text
      copyable={{
        onCopy: () => void messageApi.success(t('common.copied')),
      }}
      style={{ wordBreak: 'break-all' }}
    >
      {v}
    </Typography.Text>
  )
}

/** Build request payload from form values. */
function toPayload(values: FileStorageFormValues): FileStorageCreateBody {
  const authType = values.auth_type.trim()
  const isBasic = authType.toUpperCase() === 'BASIC'
  const isApiKey = authType.toUpperCase() === 'API_KEY'
  const storageType = values.type?.trim() || null
  const isS3 = (storageType ?? '').toUpperCase() === 'S3'
  return {
    name: values.name?.trim() || null,
    bucket_name: isS3 ? values.bucket_name?.trim() || null : null,
    type: storageType,
    enabled: values.enabled,
    auth_type: authType,
    endpoint_url: values.endpoint_url?.trim() || null,
    api_key: isApiKey ? values.api_key?.trim() || null : null,
    secret_key: isApiKey ? values.secret_key?.trim() || null : null,
    auth_name: isBasic ? values.auth_name?.trim() || null : null,
    auth_passwd: isBasic ? values.auth_passwd?.trim() || null : null,
  }
}

/** Render the system settings page for file storage CRUD. */
export function FileStoragePage() {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const { workspaceId } = useAuth()
  const [form] = Form.useForm<FileStorageFormValues>()
  const [loading, setLoading] = useState(false)
  const [items, setItems] = useState<FileStorageListItem[]>([])
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [total, setTotal] = useState(0)
  const [rev, setRev] = useState(0)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const [viewOpen, setViewOpen] = useState(false)
  const [viewLoading, setViewLoading] = useState(false)
  const [viewDetail, setViewDetail] = useState<FileStorageDetail | null>(null)
  const [updatingStatusIds, setUpdatingStatusIds] = useState<Set<string>>(new Set())
  const storageTypeDictQ = useDictItemTree(STORAGE_TYPE_DICT_CODE)
  const storageTypeItems = useMemo(
    () => storageTypeDictQ.data?.flat ?? [],
    [storageTypeDictQ.data],
  )
  const storageTypeDictLoading = storageTypeDictQ.isLoading

  const watchedAuthType = Form.useWatch('auth_type', form) ?? 'NONE'
  const watchedStorageType = Form.useWatch('type', form)
  const showBasicFields = watchedAuthType.toUpperCase() === 'BASIC'
  const showApiKeyField = watchedAuthType.toUpperCase() === 'API_KEY'
  const showBucketField = (watchedStorageType ?? '').trim().toUpperCase() === 'S3'

  const authTypeOptions = useMemo(
    () => [
      { value: 'NONE', label: t('settings.fileStorageAuthTypeNone') },
      { value: 'BASIC', label: t('settings.fileStorageAuthTypeBasic') },
      { value: 'API_KEY', label: t('settings.fileStorageAuthTypeApiKey') },
    ],
    [t],
  )

  const authTypeLabelByCanon = useMemo(() => {
    const m = new Map<string, string>()
    for (const o of authTypeOptions) {
      m.set(o.value, o.label)
    }
    return m
  }, [authTypeOptions])

  /**
   * Resolve auth_type code to localized label for table and detail views.
   * @param code Raw auth_type from list or detail payload.
   */
  const resolveAuthTypeLabel = (code: string | null | undefined) => {
    if (code == null || code.trim() === '') return '—'
    const canon = canonicalFileStorageAuthType(code)
    return authTypeLabelByCanon.get(canon) ?? '—'
  }
  const statusOptions = useMemo(
    () => [
      { value: true, label: t('settings.fileStorageStatusEnabled') },
      { value: false, label: t('settings.fileStorageStatusDisabled') },
    ],
    [t],
  )

  const storageTypeLabelByCode = useMemo(() => {
    const m = new Map<string, string>()
    for (const i of sortDictItems(storageTypeItems)) {
      m.set(i.code, i.name)
    }
    return m
  }, [storageTypeItems])

  const storageTypeSelectOptions = useMemo(
    () => sortDictItems(storageTypeItems).map((i) => ({ value: i.code, label: i.name })),
    [storageTypeItems],
  )

  const storageTypeSelectOptionsWithCurrent = useMemo(() => {
    const options = [...storageTypeSelectOptions]
    if (!open) return options
    const cur = watchedStorageType?.trim()
    if (cur && !options.some((o) => o.value === cur)) {
      options.push({
        value: cur,
        label: storageTypeLabelByCode.get(cur) ?? t('settings.fileStorageTypeNotInDict'),
      })
    }
    return options
  }, [open, storageTypeSelectOptions, storageTypeLabelByCode, t, watchedStorageType])

  /** Resolve file storage type code to display name from dictionary only (no raw code in UI). */
  const resolveStorageTypeLabel = (code: string | null | undefined) => {
    if (code == null || code === '') return '—'
    return storageTypeLabelByCode.get(code) ?? t('settings.fileStorageTypeNotInDict')
  }

  /** Load paginated file storage list. */
  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const data = await listFileStorages(workspaceId, { page, page_size: pageSize })
      const maxPage = Math.max(1, Math.ceil(data.total / pageSize) || 1)
      if (page > maxPage) {
        setPage(maxPage)
        return
      }
      setItems(data.items)
      setTotal(data.total)
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, t, workspaceId])

  useEffect(() => {
    void load()
  }, [load, rev])

  /** Open create drawer with default form values. */
  const openCreate = () => {
    setEditingId(null)
    form.resetFields()
    form.setFieldsValue({ enabled: true, auth_type: 'NONE' })
    setOpen(true)
  }

  /** Open edit drawer and preload row detail. */
  const openEdit = async (storageId: string) => {
    if (!workspaceId) return
    setEditingId(storageId)
    setSubmitting(true)
    try {
      const detail = await getFileStorage(workspaceId, storageId)
      form.setFieldsValue({
        name: detail.name ?? '',
        bucket_name: detail.bucket_name ?? '',
        type: detail.type ?? '',
        enabled: detail.enabled,
        auth_type: canonicalFileStorageAuthType(detail.auth_type),
        endpoint_url: detail.endpoint_url ?? '',
        api_key: detail.api_key ?? '',
        secret_key: detail.secret_key ?? '',
        auth_name: detail.auth_name ?? '',
        auth_passwd: detail.auth_passwd ?? '',
      })
      setOpen(true)
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setSubmitting(false)
    }
  }

  /** Open detail drawer and load row detail. */
  const openView = async (storageId: string) => {
    if (!workspaceId) return
    setViewOpen(true)
    setViewLoading(true)
    setViewDetail(null)
    try {
      const detail = await getFileStorage(workspaceId, storageId)
      setViewDetail(detail)
    } catch (e) {
      showAppError(messageApi, t, e)
      setViewOpen(false)
    } finally {
      setViewLoading(false)
    }
  }

  /** Submit create/edit form to backend. */
  const onSubmit = async (values: FileStorageFormValues) => {
    if (!workspaceId) return
    setSubmitting(true)
    try {
      const payload = toPayload(values)
      if (editingId) {
        await patchFileStorage(workspaceId, editingId, payload)
        void messageApi.success(t('settings.fileStorageUpdated'))
      } else {
        await createFileStorage(workspaceId, payload)
        void messageApi.success(t('settings.fileStorageCreated'))
        setPage(1)
      }
      setOpen(false)
      setRev((n) => n + 1)
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setSubmitting(false)
    }
  }

  /** Delete one row and refresh list. */
  const handleDelete = async (storageId: string) => {
    if (!workspaceId) return
    try {
      await deleteFileStorage(workspaceId, storageId)
      void messageApi.success(t('settings.fileStorageDeleted'))
      setRev((n) => n + 1)
    } catch (e) {
      showAppError(messageApi, t, e)
    }
  }

  /** Toggle one row status directly from table switch. */
  const handleToggleEnabled = async (storageId: string, enabled: boolean) => {
    if (!workspaceId) return
    setUpdatingStatusIds((prev) => {
      const next = new Set(prev)
      next.add(storageId)
      return next
    })
    try {
      await patchFileStorage(workspaceId, storageId, { enabled })
      setItems((prev) =>
        prev.map((item) => (item.id === storageId ? { ...item, enabled } : item)),
      )
      setViewDetail((prev) => (prev && prev.id === storageId ? { ...prev, enabled } : prev))
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setUpdatingStatusIds((prev) => {
        const next = new Set(prev)
        next.delete(storageId)
        return next
      })
    }
  }

  /** Format nullable date-time string to locale text. */
  const formatDateTime = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleString(undefined, { hour12: false }) : '—'

  const columns: ColumnsType<FileStorageListItem> = [
    {
      title: t('settings.fileStorageName'),
      dataIndex: 'name',
      key: 'name',
      width: 160,
      ellipsis: true,
      render: (v: string | null) => v?.trim() || '—',
    },
    {
      title: t('settings.fileStorageType'),
      dataIndex: 'type',
      key: 'type',
      width: 120,
      ellipsis: true,
      render: (v: string | null) => resolveStorageTypeLabel(v),
    },
    {
      title: t('settings.fileStorageBucketName'),
      dataIndex: 'bucket_name',
      key: 'bucket_name',
      width: 160,
      ellipsis: true,
      render: (v: string | null) => v?.trim() || '—',
    },
    {
      title: t('settings.fileStorageEndpointUrl'),
      dataIndex: 'endpoint_url',
      key: 'endpoint_url',
      width: 220,
      ellipsis: true,
      render: (v: string | null) => v?.trim() || '—',
    },
    {
      title: t('settings.fileStorageAuthType'),
      dataIndex: 'auth_type',
      key: 'auth_type',
      width: 160,
      ellipsis: true,
      render: (v: string | null | undefined) => resolveAuthTypeLabel(v),
    },
    {
      title: t('settings.fileStorageEnabled'),
      key: 'enabled',
      width: 120,
      render: (_, row) => (
        <Switch
          checked={row.enabled}
          checkedChildren={t('settings.fileStorageStatusEnabled')}
          unCheckedChildren={t('settings.fileStorageStatusDisabled')}
          loading={updatingStatusIds.has(row.id)}
          onChange={(checked) => void handleToggleEnabled(row.id, checked)}
        />
      ),
    },
    {
      title: t('settings.fileStorageCreatedAt'),
      dataIndex: 'create_at',
      key: 'create_at',
      width: 200,
      render: (v: string | null) => formatDateTime(v),
    },
    {
      title: t('settings.fileStorageActions'),
      key: 'actions',
      width: 160,
      render: (_, row) => (
        <Space>
          <Button
            type="text"
            icon={<EyeOutlined />}
            onClick={() => void openView(row.id)}
            aria-label={t('settings.fileStorageView')}
          />
          <Button
            type="text"
            icon={<EditOutlined />}
            onClick={() => void openEdit(row.id)}
            aria-label={t('settings.fileStorageEdit')}
          />
          <Popconfirm
            title={t('settings.fileStorageDeleteConfirm')}
            onConfirm={() => void handleDelete(row.id)}
          >
            <Button
              type="text"
              danger
              icon={<DeleteOutlined />}
              aria-label={t('settings.fileStorageDelete')}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  if (!workspaceId) {
    return (
      <div className="minerva-file-storage-settings">
        <Paragraph>{t('settings.ocrNoWorkspace')}</Paragraph>
      </div>
    )
  }

  return (
    <div className="minerva-file-storage-settings">
      <Card size="small" variant="borderless" className="minerva-file-storage-settings__card">
        <Space className="minerva-file-storage-settings__toolbar">
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {t('settings.fileStorageAdd')}
          </Button>
        </Space>
        <div className="minerva-file-storage-settings__table-wrap">
          <Table<FileStorageListItem>
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={items}
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: true,
              pageSizeOptions: [10, 20, 50, 100],
              onChange: (p, ps) => {
                setPage(p)
                setPageSize(ps)
              },
            }}
            size="middle"
            className="minerva-card-table-scroll-ocr minerva-file-storage-settings__table"
            scroll={{ x: true, y: 'calc(100dvh - 360px)' }}
            sticky
          />
        </div>
      </Card>

      <Drawer
        size={760}
        placement="right"
        open={open}
        title={editingId ? t('settings.fileStorageEdit') : t('settings.fileStorageAdd')}
        onClose={() => setOpen(false)}
        destroyOnHidden
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
        <Form form={form} layout="vertical" onFinish={(v) => void onSubmit(v)}>
          <Form.Item
            name="name"
            label={t('settings.fileStorageName')}
            rules={[{ required: true, message: t('settings.fileStorageNameRequired') }]}
          >
            <Input allowClear maxLength={32} />
          </Form.Item>
          <Form.Item name="type" label={t('settings.fileStorageType')}>
            <Select
              allowClear
              loading={storageTypeDictLoading}
              options={storageTypeSelectOptionsWithCurrent}
              optionFilterProp="label"
              showSearch
            />
          </Form.Item>
          {showBucketField ? (
            <Form.Item
              name="bucket_name"
              label={t('settings.fileStorageBucketName')}
              dependencies={['type']}
              rules={[
                {
                  validator: async (_, value) => {
                    const st = form.getFieldValue('type') as string | undefined
                    if ((st ?? '').trim().toUpperCase() !== 'S3') return
                    if (String(value ?? '').trim()) return
                    throw new Error(t('settings.fileStorageBucketNameRequired'))
                  },
                },
              ]}
            >
              <Input allowClear maxLength={63} />
            </Form.Item>
          ) : null}
          <Form.Item name="enabled" label={t('settings.fileStorageEnabled')}>
            <Select options={statusOptions} />
          </Form.Item>
          <Form.Item
            name="auth_type"
            label={t('settings.fileStorageAuthType')}
            rules={[{ required: true, message: t('settings.fileStorageAuthTypeRequired') }]}
          >
            <Select allowClear options={authTypeOptions} />
          </Form.Item>
          <Form.Item
            name="endpoint_url"
            label={t('settings.fileStorageEndpointUrl')}
            rules={[{ type: 'url', message: t('settings.ocrErrorUrl') }]}
          >
            <Input allowClear maxLength={128} />
          </Form.Item>
          {showBasicFields ? (
            <>
              <Form.Item name="auth_name" label={t('settings.fileStorageAuthName')}>
                <Input allowClear maxLength={64} />
              </Form.Item>
              <Form.Item name="auth_passwd" label={t('settings.fileStorageAuthPasswd')}>
                <Input allowClear maxLength={128} autoComplete="off" />
              </Form.Item>
            </>
          ) : null}
          {showApiKeyField ? (
            <>
              <Form.Item name="api_key" label={t('settings.fileStorageApiKey')}>
                <Input allowClear maxLength={128} autoComplete="off" />
              </Form.Item>
              <Form.Item
                name="secret_key"
                label={t('settings.fileStorageSecretKey')}
                dependencies={['auth_type']}
                rules={
                  editingId
                    ? []
                    : [
                        {
                          validator: async (_, value) => {
                            const at = form.getFieldValue('auth_type') as string | undefined
                            if ((at ?? '').toUpperCase() !== 'API_KEY') return
                            if (String(value ?? '').trim()) return
                            throw new Error(t('settings.fileStorageSecretKeyRequired'))
                          },
                        },
                      ]
                }
              >
                <Input allowClear maxLength={128} autoComplete="off" />
              </Form.Item>
            </>
          ) : null}
        </Form>
      </Drawer>

      <Drawer
        title={t('settings.fileStorageView')}
        size={760}
        placement="right"
        open={viewOpen}
        onClose={() => {
          setViewOpen(false)
          setViewDetail(null)
        }}
        destroyOnHidden
        classNames={{ body: 'minerva-scrollbar-styled' }}
      >
        {viewLoading ? (
          <Paragraph>{t('common.loading')}</Paragraph>
        ) : viewDetail ? (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label={t('settings.fileStorageName')}>
              {viewDetail.name?.trim() || '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t('settings.fileStorageType')}>
              {resolveStorageTypeLabel(viewDetail.type)}
            </Descriptions.Item>
            <Descriptions.Item label={t('settings.fileStorageBucketName')}>
              {renderCopyable(viewDetail.bucket_name, t, messageApi)}
            </Descriptions.Item>
            <Descriptions.Item label={t('settings.fileStorageEnabled')}>
              {viewDetail.enabled
                ? t('settings.fileStorageStatusEnabled')
                : t('settings.fileStorageStatusDisabled')}
            </Descriptions.Item>
            <Descriptions.Item label={t('settings.fileStorageAuthType')}>
              {resolveAuthTypeLabel(viewDetail.auth_type)}
            </Descriptions.Item>
            <Descriptions.Item label={t('settings.fileStorageEndpointUrl')}>
              {renderCopyable(viewDetail.endpoint_url, t, messageApi)}
            </Descriptions.Item>
            {canonicalFileStorageAuthType(viewDetail.auth_type) === 'API_KEY' ? (
              <>
                <Descriptions.Item label={t('settings.fileStorageApiKey')}>
                  {renderCopyable(viewDetail.api_key, t, messageApi)}
                </Descriptions.Item>
                <Descriptions.Item label={t('settings.fileStorageSecretKey')}>
                  {renderCopyable(viewDetail.secret_key, t, messageApi)}
                </Descriptions.Item>
              </>
            ) : null}
            <Descriptions.Item label={t('settings.fileStorageAuthName')}>
              {renderCopyable(viewDetail.auth_name, t, messageApi)}
            </Descriptions.Item>
            <Descriptions.Item label={t('settings.fileStorageAuthPasswd')}>
              {renderCopyable(viewDetail.auth_passwd, t, messageApi)}
            </Descriptions.Item>
            <Descriptions.Item label={t('settings.fileStorageCreatedAt')}>
              {formatDateTime(viewDetail.create_at)}
            </Descriptions.Item>
            <Descriptions.Item label={t('settings.fileStorageUpdatedAt')}>
              {formatDateTime(viewDetail.update_at)}
            </Descriptions.Item>
          </Descriptions>
        ) : null}
      </Drawer>
    </div>
  )
}
