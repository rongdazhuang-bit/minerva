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
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/api/client'
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
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import { useDictItemTree } from '@/hooks/useDictItemTree'
import './FileStoragePage.css'

const { Paragraph } = Typography
const STORAGE_TYPE_DICT_CODE = 'STORGE_TYPE'

/** Form values used by create/edit file storage drawer. */
type FileStorageFormValues = {
  name?: string
  type?: string
  enabled: boolean
  auth_type: string
  endpoint_url?: string
  api_key?: string
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

/** Show API errors if available, else fallback message. */
function showErr(t: (key: string) => string, e: unknown) {
  if (e instanceof ApiError) {
    void message.error(e.message)
    return
  }
  void message.error(t('common.error'))
}

/** Render copyable text for non-empty plain values. */
function renderCopyable(value: string | null | undefined, t: (key: string) => string) {
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

/** Build request payload from form values. */
function toPayload(values: FileStorageFormValues): FileStorageCreateBody {
  const authType = values.auth_type.trim()
  const isBasic = authType.toUpperCase() === 'BASIC'
  const isApiKey = authType.toUpperCase() === 'API_KEY'
  return {
    name: values.name?.trim() || null,
    type: values.type?.trim() || null,
    enabled: values.enabled,
    auth_type: authType,
    endpoint_url: values.endpoint_url?.trim() || null,
    api_key: isApiKey ? values.api_key?.trim() || null : null,
    auth_name: isBasic ? values.auth_name?.trim() || null : null,
    auth_passwd: isBasic ? values.auth_passwd?.trim() || null : null,
  }
}

/** Render the system settings page for file storage CRUD. */
export function FileStoragePage() {
  const { t } = useTranslation()
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

  const authTypeOptions = useMemo(
    () => [
      { value: 'NONE', label: t('settings.fileStorageAuthTypeNone') },
      { value: 'BASIC', label: t('settings.fileStorageAuthTypeBasic') },
      { value: 'API_KEY', label: t('settings.fileStorageAuthTypeApiKey') },
    ],
    [t],
  )
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
      options.push({ value: cur, label: cur })
    }
    return options
  }, [open, storageTypeSelectOptions, watchedStorageType])

  /** Resolve file storage type code to display label from dictionary. */
  const resolveStorageTypeLabel = (code: string | null | undefined) => {
    if (code == null || code === '') return '—'
    return storageTypeLabelByCode.get(code) ?? code
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
      showErr(t, e)
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
        type: detail.type ?? '',
        enabled: detail.enabled,
        auth_type: detail.auth_type || 'NONE',
        endpoint_url: detail.endpoint_url ?? '',
        api_key: detail.api_key ?? '',
        auth_name: detail.auth_name ?? '',
        auth_passwd: detail.auth_passwd ?? '',
      })
      setOpen(true)
    } catch (e) {
      showErr(t, e)
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
      showErr(t, e)
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
        void message.success(t('settings.fileStorageUpdated'))
      } else {
        await createFileStorage(workspaceId, payload)
        void message.success(t('settings.fileStorageCreated'))
        setPage(1)
      }
      setOpen(false)
      setRev((n) => n + 1)
    } catch (e) {
      showErr(t, e)
    } finally {
      setSubmitting(false)
    }
  }

  /** Delete one row and refresh list. */
  const handleDelete = async (storageId: string) => {
    if (!workspaceId) return
    try {
      await deleteFileStorage(workspaceId, storageId)
      void message.success(t('settings.fileStorageDeleted'))
      setRev((n) => n + 1)
    } catch (e) {
      showErr(t, e)
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
      showErr(t, e)
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
      width: 180,
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
        width={760}
        placement="right"
        open={open}
        title={editingId ? t('settings.fileStorageEdit') : t('settings.fileStorageAdd')}
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
        <Form form={form} layout="vertical" onFinish={(v) => void onSubmit(v)}>
          <Form.Item name="name" label={t('settings.fileStorageName')}>
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
                <Input.Password allowClear maxLength={128} />
              </Form.Item>
            </>
          ) : null}
          {showApiKeyField ? (
            <Form.Item name="api_key" label={t('settings.fileStorageApiKey')}>
              <Input.Password allowClear maxLength={128} />
            </Form.Item>
          ) : null}
        </Form>
      </Drawer>

      <Drawer
        title={t('settings.fileStorageView')}
        width={760}
        placement="right"
        open={viewOpen}
        onClose={() => {
          setViewOpen(false)
          setViewDetail(null)
        }}
        destroyOnClose
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
            <Descriptions.Item label={t('settings.fileStorageEnabled')}>
              {viewDetail.enabled
                ? t('settings.fileStorageStatusEnabled')
                : t('settings.fileStorageStatusDisabled')}
            </Descriptions.Item>
            <Descriptions.Item label={t('settings.fileStorageAuthType')}>
              {viewDetail.auth_type}
            </Descriptions.Item>
            <Descriptions.Item label={t('settings.fileStorageEndpointUrl')}>
              {renderCopyable(viewDetail.endpoint_url, t)}
            </Descriptions.Item>
            <Descriptions.Item label={t('settings.fileStorageApiKey')}>
              {renderCopyable(viewDetail.api_key, t)}
            </Descriptions.Item>
            <Descriptions.Item label={t('settings.fileStorageAuthName')}>
              {renderCopyable(viewDetail.auth_name, t)}
            </Descriptions.Item>
            <Descriptions.Item label={t('settings.fileStorageAuthPasswd')}>
              {renderCopyable(viewDetail.auth_passwd, t)}
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
