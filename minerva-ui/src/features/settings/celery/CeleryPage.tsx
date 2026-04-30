/** Renders workspace celery jobs list page with action column operations. */

import { DeleteOutlined, EditOutlined, PlayCircleOutlined, StopOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import {
  deleteCeleryJob,
  listCeleryJobs,
  runCeleryJobNow,
  startCeleryJob,
  stopCeleryJob,
} from './api'
import type { CeleryJob, CeleryJobListParams } from './types'

type FilterFormValues = {
  name?: string
  task_code?: string
  task?: string
  enabled?: 'true' | 'false'
}

/** Converts UTC/ISO date-time value into user locale string. */
function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString(undefined, { hour12: false }) : '—'
}

/** Renders last execution status with a compact semantic tag. */
function renderLastStatus(status: string | null | undefined, t: (key: string) => string) {
  const normalized = status?.trim().toUpperCase() ?? ''
  if (normalized === '') return '—'
  if (normalized === 'SUCCESS') return <Tag color="success">{t('settings.celery.statusSuccess')}</Tag>
  if (normalized === 'FAILED') return <Tag color="error">{t('settings.celery.statusFailed')}</Tag>
  if (normalized === 'PROCESS' || normalized === 'RUNNING') {
    return <Tag color="processing">{t('settings.celery.statusRunning')}</Tag>
  }
  return <Tag>{normalized}</Tag>
}

/** Normalizes filter form values into list API query params. */
function toListParams(values: FilterFormValues): CeleryJobListParams {
  return {
    name: values.name?.trim() || undefined,
    task_code: values.task_code?.trim() || undefined,
    task: values.task?.trim() || undefined,
    enabled:
      values.enabled == null
        ? undefined
        : values.enabled === 'true',
  }
}

/** Hosts filters, table pagination, and operation buttons for celery jobs. */
export function CeleryPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const [filterForm] = Form.useForm<FilterFormValues>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [filters, setFilters] = useState<CeleryJobListParams>({})
  const [refreshTick, setRefreshTick] = useState(0)
  const [editOpen, setEditOpen] = useState(false)
  const [editingRow, setEditingRow] = useState<CeleryJob | null>(null)
  const [actionLoadingMap, setActionLoadingMap] = useState<Record<string, boolean>>({})

  const listQuery = useQuery({
    queryKey: ['celeryJobs', workspaceId, page, pageSize, filters, refreshTick],
    queryFn: () =>
      listCeleryJobs(workspaceId!, {
        ...filters,
        page,
        page_size: pageSize,
      }),
    enabled: Boolean(workspaceId),
  })

  /** Keeps row-level button loading state isolated by action key. */
  const setActionLoading = (key: string, loading: boolean) => {
    setActionLoadingMap((prev) => ({ ...prev, [key]: loading }))
  }

  /** Reloads list after one action succeeds. */
  const reloadList = () => {
    setRefreshTick((v) => v + 1)
  }

  /** Applies current filters and resets paging to first page. */
  const handleSearch = (values: FilterFormValues) => {
    setPage(1)
    setFilters(toListParams(values))
  }

  /** Clears all filters and re-queries from first page. */
  const handleReset = () => {
    filterForm.resetFields()
    setPage(1)
    setFilters({})
  }

  /** Opens placeholder edit modal for one celery job row. */
  const openEditModal = (row: CeleryJob) => {
    setEditingRow(row)
    setEditOpen(true)
  }

  /** Closes placeholder edit modal and clears selected row. */
  const closeEditModal = () => {
    setEditOpen(false)
    setEditingRow(null)
  }

  /** Deletes one celery job row and refreshes table data. */
  const handleDelete = async (row: CeleryJob) => {
    if (!workspaceId) return
    const actionKey = `${row.id}-delete`
    setActionLoading(actionKey, true)
    try {
      await deleteCeleryJob(workspaceId, row.id)
      void message.success(t('settings.celery.deleted'))
      reloadList()
    } catch (error) {
      void message.error(error instanceof ApiError ? error.message : t('common.error'))
    } finally {
      setActionLoading(actionKey, false)
    }
  }

  /** Sends run-now command for one row and displays backend task id. */
  const handleRunNow = async (row: CeleryJob) => {
    if (!workspaceId) return
    const actionKey = `${row.id}-run-now`
    setActionLoading(actionKey, true)
    try {
      const out = await runCeleryJobNow(workspaceId, row.id)
      void message.success(t('settings.celery.runNowAccepted', { taskId: out.task_id }))
      reloadList()
    } catch (error) {
      void message.error(error instanceof ApiError ? error.message : t('common.error'))
    } finally {
      setActionLoading(actionKey, false)
    }
  }

  /** Toggles one row between enabled(start) and disabled(stop) states. */
  const handleToggleEnabled = async (row: CeleryJob) => {
    if (!workspaceId) return
    const actionKey = `${row.id}-toggle`
    setActionLoading(actionKey, true)
    try {
      if (row.enabled) {
        await stopCeleryJob(workspaceId, row.id)
        void message.success(t('settings.celery.stopped'))
      } else {
        await startCeleryJob(workspaceId, row.id)
        void message.success(t('settings.celery.enabled'))
      }
      reloadList()
    } catch (error) {
      void message.error(error instanceof ApiError ? error.message : t('common.error'))
    } finally {
      setActionLoading(actionKey, false)
    }
  }

  const columns: ColumnsType<CeleryJob> = useMemo(
    () => [
      {
        title: t('settings.celery.colName'),
        dataIndex: 'name',
        key: 'name',
        width: 160,
        ellipsis: true,
      },
      {
        title: t('settings.celery.colTaskCode'),
        dataIndex: 'task_code',
        key: 'task_code',
        width: 160,
        ellipsis: true,
      },
      {
        title: t('settings.celery.colTask'),
        dataIndex: 'task',
        key: 'task',
        width: 220,
        ellipsis: true,
      },
      {
        title: t('settings.celery.colCron'),
        dataIndex: 'cron',
        key: 'cron',
        width: 140,
        render: (value: string | null) => value ?? '—',
      },
      {
        title: t('settings.celery.colEnabled'),
        dataIndex: 'enabled',
        key: 'enabled',
        width: 110,
        render: (value: boolean) =>
          value ? (
            <Tag color="success">{t('settings.celery.enabledText')}</Tag>
          ) : (
            <Tag>{t('settings.celery.disabledText')}</Tag>
          ),
      },
      {
        title: t('settings.celery.colNextRunAt'),
        dataIndex: 'next_run_at',
        key: 'next_run_at',
        width: 190,
        render: (value: string | null) => formatDateTime(value),
      },
      {
        title: t('settings.celery.colLastRunAt'),
        dataIndex: 'last_run_at',
        key: 'last_run_at',
        width: 190,
        render: (value: string | null) => formatDateTime(value),
      },
      {
        title: t('settings.celery.colLastStatus'),
        dataIndex: 'last_status',
        key: 'last_status',
        width: 140,
        render: (value: string | null) => renderLastStatus(value, t),
      },
      {
        title: t('settings.celery.colRemark'),
        dataIndex: 'remark',
        key: 'remark',
        width: 240,
        ellipsis: true,
        render: (value: string | null) => value ?? '—',
      },
      {
        title: t('settings.celery.colActions'),
        key: 'actions',
        width: 260,
        fixed: 'right',
        render: (_, row) => (
          <Space size={2}>
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={() => openEditModal(row)}
              aria-label={t('settings.celery.actionEdit')}
            />
            <Popconfirm
              title={t('settings.celery.deleteConfirm')}
              onConfirm={() => void handleDelete(row)}
            >
              <Button
                type="text"
                danger
                loading={Boolean(actionLoadingMap[`${row.id}-delete`])}
                icon={<DeleteOutlined />}
                aria-label={t('settings.celery.actionDelete')}
              />
            </Popconfirm>
            <Button
              type="text"
              icon={<PlayCircleOutlined />}
              loading={Boolean(actionLoadingMap[`${row.id}-run-now`])}
              onClick={() => void handleRunNow(row)}
              aria-label={t('settings.celery.actionRunNow')}
            />
            <Button
              type="text"
              icon={<StopOutlined />}
              loading={Boolean(actionLoadingMap[`${row.id}-toggle`])}
              onClick={() => void handleToggleEnabled(row)}
              aria-label={
                row.enabled ? t('settings.celery.actionStop') : t('settings.celery.actionEnable')
              }
            />
          </Space>
        ),
      },
    ],
    [actionLoadingMap, t],
  )

  if (!workspaceId) {
    return (
      <div className="minerva-celery-page">
        <Empty description={t('settings.celeryNoWorkspace')} style={{ color: 'var(--minerva-ink)' }} />
      </div>
    )
  }

  return (
    <div className="minerva-celery-page">
      <Card size="small" variant="borderless">
        <Form form={filterForm} layout="inline" onFinish={handleSearch}>
          <Form.Item name="name" label={t('settings.celery.filterName')}>
            <Input allowClear placeholder={t('settings.celery.filterNamePh')} />
          </Form.Item>
          <Form.Item name="task_code" label={t('settings.celery.filterTaskCode')}>
            <Input allowClear placeholder={t('settings.celery.filterTaskCodePh')} />
          </Form.Item>
          <Form.Item name="task" label={t('settings.celery.filterTask')}>
            <Input allowClear placeholder={t('settings.celery.filterTaskPh')} />
          </Form.Item>
          <Form.Item name="enabled" label={t('settings.celery.filterEnabled')}>
            <Select
              allowClear
              style={{ minWidth: 140 }}
              options={[
                { value: 'true', label: t('settings.celery.enabledText') },
                { value: 'false', label: t('settings.celery.disabledText') },
              ]}
            />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button htmlType="submit" type="primary">
                {t('rules.search')}
              </Button>
              <Button onClick={handleReset}>{t('rules.resetFilter')}</Button>
            </Space>
          </Form.Item>
        </Form>

        {listQuery.error != null && (
          <Alert
            type="error"
            showIcon
            style={{ marginTop: 12, marginBottom: 12 }}
            message={listQuery.error instanceof ApiError ? listQuery.error.message : t('common.error')}
          />
        )}

        <Table<CeleryJob>
          rowKey="id"
          style={{ marginTop: 12 }}
          loading={listQuery.isFetching}
          columns={columns}
          dataSource={listQuery.data?.items ?? []}
          pagination={{
            current: page,
            pageSize,
            total: listQuery.data?.total ?? 0,
            showSizeChanger: true,
            pageSizeOptions: [10, 20, 50, 100],
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage)
              setPageSize(nextPageSize)
            },
          }}
          scroll={{ x: 1900, y: 'calc(100dvh - 380px)' }}
          sticky
        />
      </Card>

      <Modal
        open={editOpen}
        title={t('settings.celery.editModalTitle')}
        onCancel={closeEditModal}
        onOk={closeEditModal}
      >
        <Typography.Paragraph style={{ marginBottom: 8 }}>
          {t('settings.celery.editPlaceholder')}
        </Typography.Paragraph>
        <Typography.Text type="secondary">
          {editingRow == null
            ? '—'
            : `${t('settings.celery.colName')}: ${editingRow.name} / ${t('settings.celery.colTaskCode')}: ${editingRow.task_code}`}
        </Typography.Text>
      </Modal>
    </div>
  )
}
