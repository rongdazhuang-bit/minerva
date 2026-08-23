/**
 * Graph knowledge base list: name / admin-scope filters, table, and create entry.
 */
import { DeleteOutlined, FileAddOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Empty, Form, Input, Popconfirm, Select, Space, Table, Tag, Tooltip, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/app/AuthContext'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import {
  deleteGraphKb,
  listGraphKbs,
  type GraphKbListParams,
  type GraphKbOut,
} from '@/features/graph-kb/api/graphKb'
import { indexingStatusColor } from '@/features/graph-kb/shared/graphKbForm'
import './GraphKbListPage.css'

/** Vertical space reserved below the table body for pagination and chrome. */
const TABLE_SCROLL_GUTTER_PX = 48

type FilterFormValues = {
  name?: string
  scope?: 'all' | 'mine'
}

/** Maps filter form values to GraphKB list query params. */
function toListParams(
  values: FilterFormValues,
  page: number,
  canFilterMine: boolean,
): GraphKbListParams {
  const params: GraphKbListParams = { page, page_size: DEFAULT_PAGE_SIZE }
  if (values.name?.trim()) params.name = values.name.trim()
  if (canFilterMine && values.scope === 'mine') params.mine_only = true
  return params
}

/** GraphKB list page at `/app/graph-kb`. */
export function GraphKbListPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { workspaceId, isWorkspaceAdmin, isSuperAdmin, userId } = useAuth()
  const canFilterMine = isWorkspaceAdmin || isSuperAdmin
  const [filterForm] = Form.useForm<FilterFormValues>()
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState<GraphKbListParams>({ page: 1, page_size: DEFAULT_PAGE_SIZE })
  const tableWrapRef = useRef<HTMLDivElement | null>(null)
  /** Computed Ant Design Table body `scroll.y` from the flex table region height. */
  const [tableBodyScrollY, setTableBodyScrollY] = useState(420)
  /** Computed Ant Design Table body `scroll.x` from the flex table region width. */
  const [tableScrollX, setTableScrollX] = useState(0)

  const listQ = useQuery({
    queryKey: ['graph-kbs', workspaceId, filters],
    queryFn: () => listGraphKbs(workspaceId!, filters),
    enabled: Boolean(workspaceId),
  })

  const deleteM = useMutation({
    mutationFn: (id: string) => deleteGraphKb(workspaceId!, id),
    onSuccess: () => {
      message.success(t('graphKb.list.deleteSuccess'))
      void queryClient.invalidateQueries({ queryKey: ['graph-kbs', workspaceId] })
    },
    onError: (err: Error) => message.error(err.message),
  })

  const onSearch = useCallback(
    (values: FilterFormValues) => {
      setPage(1)
      setFilters(toListParams(values, 1, canFilterMine))
    },
    [canFilterMine],
  )

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
  }, [workspaceId, listQ.data?.items?.length, page])

  const columns: ColumnsType<GraphKbOut> = useMemo(
    () => [
      {
        title: t('graphKb.list.column.name'),
        dataIndex: 'name',
        key: 'name',
        render: (name: string, row) => (
          <Button type="link" style={{ padding: 0 }} onClick={() => navigate(`/app/graph-kb/${row.id}/documents`)}>
            {name}
          </Button>
        ),
      },
      {
        title: t('graphKb.list.column.engine'),
        dataIndex: 'engine',
        key: 'engine',
        width: 120,
        render: (engine: string) => t(`graphKb.engine.${engine}`, { defaultValue: engine }),
      },
      {
        title: t('graphKb.list.column.permission'),
        dataIndex: 'permission',
        key: 'permission',
        width: 160,
        render: (permission: string) =>
          t(`graphKb.permission.${permission}`, { defaultValue: permission }),
      },
      {
        title: t('graphKb.list.column.indexing'),
        dataIndex: 'indexing_status',
        key: 'indexing_status',
        width: 120,
        render: (status: string) => (
          <Tag color={indexingStatusColor(status)}>
            {t(`graphKb.status.${status}`, { defaultValue: status })}
          </Tag>
        ),
      },
      {
        title: t('graphKb.list.column.createdAt'),
        dataIndex: 'create_at',
        key: 'create_at',
        width: 180,
        render: (v: string | null) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '—'),
      },
      {
        title: t('graphKb.list.column.actions'),
        key: 'actions',
        width: 72,
        render: (_: unknown, row) => {
          // Hide delete unless the viewer is admin/super-admin or the creator.
          const canDelete = isWorkspaceAdmin || isSuperAdmin || row.created_by === userId
          if (!canDelete) return null
          return (
            <Tooltip title={t('graphKb.list.delete')}>
              <span>
                <Popconfirm
                  title={t('graphKb.list.deleteConfirm')}
                  okText={t('common.yes')}
                  cancelText={t('common.cancel')}
                  okButtonProps={{ danger: true }}
                  onConfirm={() => deleteM.mutate(row.id)}
                >
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    loading={deleteM.isPending && deleteM.variables === row.id}
                    aria-label={t('graphKb.list.delete')}
                  />
                </Popconfirm>
              </span>
            </Tooltip>
          )
        },
      },
    ],
    [deleteM, isSuperAdmin, isWorkspaceAdmin, navigate, t, userId],
  )

  if (!workspaceId) {
    return <Empty description={t('settings.ocrNoWorkspace')} style={{ color: 'var(--minerva-ink)' }} />
  }

  return (
    <div className="minerva-graph-kb-list-page">
      <Card size="small" variant="borderless" className="minerva-graph-kb-list-page__card minerva-page-shell-card">
        <Form
          form={filterForm}
          layout="inline"
          onFinish={onSearch}
          className="minerva-graph-kb-list-page__filter"
        >
          <Form.Item name="name">
            <Input allowClear placeholder={t('graphKb.list.filter.namePh')} style={{ minWidth: 160 }} />
          </Form.Item>
          {canFilterMine ? (
            <Form.Item name="scope">
              <Select
                allowClear
                placeholder={t('graphKb.list.filter.scope')}
                style={{ minWidth: 140 }}
                options={[
                  { value: 'all', label: t('graphKb.list.filter.scopeAll') },
                  { value: 'mine', label: t('graphKb.list.filter.scopeMine') },
                ]}
              />
            </Form.Item>
          ) : null}
          <Form.Item>
            <Space wrap>
              <Button type="primary" htmlType="submit">
                {t('rules.search')}
              </Button>
              <Button onClick={onReset}>{t('rules.resetFilter')}</Button>
              <Button type="dashed" icon={<FileAddOutlined />} onClick={() => navigate('/app/graph-kb/create')}>
                {t('graphKb.list.create')}
              </Button>
            </Space>
          </Form.Item>
        </Form>

        <div ref={tableWrapRef} className="minerva-graph-kb-list-page__table-wrap">
          <Table<GraphKbOut>
            rowKey="id"
            loading={listQ.isLoading}
            columns={columns}
            dataSource={listQ.data?.items ?? []}
            locale={{ emptyText: t('graphKb.list.empty') }}
            className="minerva-graph-kb-list-page__table minerva-card-table-scroll-ocr"
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
  )
}
