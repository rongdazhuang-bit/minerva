/**
 * Knowledge base list: inline filters, table, and fullscreen create modal.
 */
import { DeleteOutlined, FileAddOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button,
  Card,
  DatePicker,
  Empty,
  Form,
  Input,
  Popconfirm,
  Space,
  Table,
  Tag,
  Tooltip,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { Dayjs } from 'dayjs'
import dayjs from 'dayjs'
import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/app/AuthContext'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import {
  listDatasets,
  type DatasetListItem,
  type DatasetListParams,
} from '@/features/dataset/api/datasets'
import { deleteDataset } from '@/features/dataset/api/documents'
import { DatasetCreateWizardModal } from '@/features/dataset/create/DatasetCreateWizardModal'
import './DatasetListPage.css'

/** Vertical space reserved below the table body for pagination and chrome (matches translate list). */
const TABLE_SCROLL_GUTTER_PX = 48

type FilterFormValues = {
  name?: string
  create_range?: [Dayjs, Dayjs]
}

/** Maps filter form values to dataset list query params. */
function toListParams(values: FilterFormValues, page: number): DatasetListParams {
  const params: DatasetListParams = { page, page_size: DEFAULT_PAGE_SIZE }
  if (values.name?.trim()) params.name = values.name.trim()
  const range = values.create_range
  if (range?.[0]) params.created_from = range[0].startOf('day').toISOString()
  if (range?.[1]) params.created_to = range[1].endOf('day').toISOString()
  return params
}

/** Knowledge base list page at `/app/dataset`. */
export function DatasetListPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { workspaceId } = useAuth()
  const [filterForm] = Form.useForm<FilterFormValues>()
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState<DatasetListParams>({ page: 1, page_size: DEFAULT_PAGE_SIZE })
  const [createOpen, setCreateOpen] = useState(false)
  const tableWrapRef = useRef<HTMLDivElement | null>(null)
  /** Computed Ant Design Table body `scroll.y` from the flex table region height. */
  const [tableBodyScrollY, setTableBodyScrollY] = useState(420)
  /** Computed Ant Design Table body `scroll.x` from the flex table region width. */
  const [tableScrollX, setTableScrollX] = useState(0)

  const listQ = useQuery({
    queryKey: ['datasets', workspaceId, filters],
    queryFn: () => listDatasets(workspaceId!, filters),
    enabled: Boolean(workspaceId),
  })

  const deleteM = useMutation({
    mutationFn: (id: string) => deleteDataset(workspaceId!, id),
    onSuccess: () => {
      message.success(t('dataset.list.deleteSuccess'))
      void queryClient.invalidateQueries({ queryKey: ['datasets', workspaceId] })
    },
    onError: (err: Error) => message.error(err.message),
  })

  const onSearch = useCallback((values: FilterFormValues) => {
    setPage(1)
    setFilters(toListParams(values, 1))
  }, [])

  const onReset = useCallback(() => {
    filterForm.resetFields()
    setPage(1)
    setFilters({ page: 1, page_size: DEFAULT_PAGE_SIZE })
  }, [filterForm])

  useLayoutEffect(() => {
    const wrap = tableWrapRef.current
    if (wrap == null) return
    const measure = () => {
      const rect = wrap.getBoundingClientRect()
      setTableBodyScrollY(Math.max(160, Math.floor(rect.height - TABLE_SCROLL_GUTTER_PX)))
      setTableScrollX(Math.max(0, Math.floor(rect.width)))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(wrap)
    return () => {
      ro.disconnect()
    }
  }, [workspaceId, createOpen, listQ.data?.items?.length, page])

  const columns: ColumnsType<DatasetListItem> = useMemo(
    () => [
      {
        title: t('dataset.list.column.name'),
        dataIndex: 'name',
        key: 'name',
        render: (name: string, row) => (
          <Button type="link" style={{ padding: 0 }} onClick={() => navigate(`/app/dataset/${row.id}/documents`)}>
            {name}
          </Button>
        ),
      },
      {
        title: t('dataset.list.column.documents'),
        dataIndex: 'document_count',
        key: 'document_count',
        width: 100,
      },
      {
        title: t('dataset.list.column.indexing'),
        dataIndex: 'indexing_technique',
        key: 'indexing_technique',
        width: 120,
        render: (v: string | null) =>
          v ? (
            <Tag color={v === 'high_quality' ? 'blue' : 'default'}>
              {v === 'high_quality' ? t('dataset.indexing.highQuality') : t('dataset.indexing.economy')}
            </Tag>
          ) : (
            '—'
          ),
      },
      {
        title: t('dataset.list.column.createdAt'),
        dataIndex: 'create_at',
        key: 'create_at',
        width: 180,
        render: (v: string | null) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '—'),
      },
      {
        title: t('dataset.documents.column.actions'),
        key: 'actions',
        width: 72,
        render: (_: unknown, row) => (
          <Tooltip title={t('dataset.list.delete')}>
            <span>
              <Popconfirm
                title={t('dataset.list.deleteConfirm')}
                onConfirm={() => deleteM.mutate(row.id)}
              >
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  loading={deleteM.isPending && deleteM.variables === row.id}
                  aria-label={t('dataset.list.delete')}
                />
              </Popconfirm>
            </span>
          </Tooltip>
        ),
      },
    ],
    [deleteM, navigate, t],
  )

  if (!workspaceId) {
    return <Empty description={t('settings.ocrNoWorkspace')} style={{ color: 'var(--minerva-ink)' }} />
  }

  return (
    <>
      <div className="minerva-dataset-list-page">
        <Card size="small" variant="borderless" className="minerva-dataset-list-page__card minerva-page-shell-card">
          <Form
            form={filterForm}
            layout="inline"
            onFinish={onSearch}
            className="minerva-dataset-list-page__filter"
          >
            <Form.Item name="name">
              <Input allowClear placeholder={t('dataset.list.filter.knowledgeBasePh')} style={{ minWidth: 160 }} />
            </Form.Item>
            <Form.Item name="create_range">
              <DatePicker.RangePicker
                allowClear
                placeholder={[
                  t('dataset.list.filter.createRangeStart'),
                  t('dataset.list.filter.createRangeEnd'),
                ]}
              />
            </Form.Item>
            <Form.Item>
              <Space wrap>
                <Button type="primary" htmlType="submit">
                  {t('rules.search')}
                </Button>
                <Button onClick={onReset}>{t('rules.resetFilter')}</Button>
                <Button type="dashed" icon={<FileAddOutlined />} onClick={() => setCreateOpen(true)}>
                  {t('dataset.list.create')}
                </Button>
              </Space>
            </Form.Item>
          </Form>

          <div ref={tableWrapRef} className="minerva-dataset-list-page__table-wrap">
            <Table<DatasetListItem>
              rowKey="id"
              loading={listQ.isLoading}
              columns={columns}
              dataSource={listQ.data?.items ?? []}
              locale={{ emptyText: t('dataset.list.empty') }}
              className="minerva-dataset-list-page__table minerva-card-table-scroll-ocr"
              scroll={{ x: tableScrollX > 0 ? tableScrollX : undefined, y: tableBodyScrollY }}
              sticky
              pagination={{
                current: page,
                pageSize: DEFAULT_PAGE_SIZE,
                total: listQ.data?.total ?? 0,
                showSizeChanger: false,
                onChange: (p) => {
                  setPage(p)
                  setFilters((prev) => ({ ...prev, page: p }))
                },
              }}
            />
          </div>
        </Card>
      </div>

      <DatasetCreateWizardModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSuccess={(id) => {
          setCreateOpen(false)
          void queryClient.invalidateQueries({ queryKey: ['datasets', workspaceId] })
          navigate(`/app/dataset/${id}/documents`)
        }}
      />
    </>
  )
}
