/** Document list for one knowledge base. */
import {
  DeleteOutlined,
  EditOutlined,
  FileTextOutlined,
  MoreOutlined,
  PlusOutlined,
  RedoOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button,
  Card,
  Dropdown,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  message,
} from 'antd'
import type { MenuProps } from 'antd'
import type { ColumnsType, TableRowSelection } from 'antd/es/table/interface'
import dayjs from 'dayjs'
import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { useAuth } from '@/app/AuthContext'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import {
  deleteDocument,
  listDocuments,
  patchDocument,
  retryDocument,
  retryFailedDocuments,
  setDocumentEnabled,
  type DatasetDocument,
} from '@/features/dataset/api/documents'
import { DatasetCreateWizardModal } from '@/features/dataset/create/DatasetCreateWizardModal'
import { DocumentSegmentModal } from '@/features/dataset/documents/DocumentSegmentModal'
import './DocumentListPage.css'

/** Vertical space reserved below the table body for pagination and chrome. */
const TABLE_SCROLL_GUTTER_PX = 48

const DOC_FORM_I18N: Record<string, string> = {
  text_model: 'dataset.documents.segmentMode.text',
  hierarchical_model: 'dataset.documents.segmentMode.hierarchical',
  qa_model: 'dataset.documents.segmentMode.qa',
}

const STATUS_DOT_CLASS: Record<string, string> = {
  available: 'minerva-document-list-page__status-dot--available',
  indexing: 'minerva-document-list-page__status-dot--indexing',
  error: 'minerva-document-list-page__status-dot--error',
  disabled: 'minerva-document-list-page__status-dot--disabled',
  paused: 'minerva-document-list-page__status-dot--paused',
  archived: 'minerva-document-list-page__status-dot--archived',
}

/** Format character counts like Dify (e.g. 23.8k). */
function formatCharacterCount(value: number | null | undefined): string {
  if (value == null) return '—'
  if (value >= 1000) {
    const compact = value / 1000
    return `${compact.toFixed(1).replace(/\.0$/, '')}k`
  }
  return String(value)
}

/** Format upload time as `YYYY-MM-DD HH:mm`. */
function formatUploadedAt(value: string | null | undefined): string {
  if (!value) return '—'
  return dayjs(value).format('YYYY-MM-DD HH:mm')
}

/** Lists documents within one knowledge base. */
export function DocumentListPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const { datasetId = '' } = useParams()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<{ keyword?: string }>()
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState<string | undefined>()
  const [appendOpen, setAppendOpen] = useState(false)
  const [renameDoc, setRenameDoc] = useState<DatasetDocument | null>(null)
  const [renameForm] = Form.useForm<{ name: string }>()
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])
  const [togglingId, setTogglingId] = useState<string | null>(null)
  const tableWrapRef = useRef<HTMLDivElement | null>(null)
  const [tableBodyScrollY, setTableBodyScrollY] = useState(420)
  const [tableScrollX, setTableScrollX] = useState(0)
  const [segmentModal, setSegmentModal] = useState<{
    documentId: string
    mode: 'view' | 'config'
  } | null>(null)

  const openSegmentView = useCallback((documentId: string) => {
    setSegmentModal({ documentId, mode: 'view' })
  }, [])

  const openSegmentConfig = useCallback((documentId: string) => {
    setSegmentModal({ documentId, mode: 'config' })
  }, [])

  const listQ = useQuery({
    queryKey: ['dataset-documents', workspaceId, datasetId, page, keyword],
    queryFn: () =>
      listDocuments(workspaceId!, datasetId, {
        page,
        page_size: DEFAULT_PAGE_SIZE,
        keyword,
      }),
    enabled: Boolean(workspaceId && datasetId),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      return items.some((item) => item.display_status === 'indexing') ? 3000 : false
    },
  })

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['dataset-documents', workspaceId, datasetId] })
    void queryClient.invalidateQueries({ queryKey: ['dataset-detail', workspaceId, datasetId] })
  }, [datasetId, queryClient, workspaceId])

  const hasFailedDocs = useMemo(
    () => (listQ.data?.items ?? []).some((item) => item.display_status === 'error'),
    [listQ.data?.items],
  )

  useLayoutEffect(() => {
    const wrap = tableWrapRef.current
    if (wrap == null) return
    const measure = () => {
      const rect = wrap.getBoundingClientRect()
      setTableBodyScrollY(Math.max(160, Math.floor(rect.height - TABLE_SCROLL_GUTTER_PX)))
      setTableScrollX(Math.max(1040, Math.floor(rect.width)))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(wrap)
    return () => {
      ro.disconnect()
    }
  }, [appendOpen, keyword, listQ.data?.items?.length, page, workspaceId])

  const openRename = useCallback(
    (row: DatasetDocument) => {
      setRenameDoc(row)
      renameForm.setFieldsValue({ name: row.name })
    },
    [renameForm],
  )

  const toggleEnabled = useCallback(
    (row: DatasetDocument, enabled: boolean) => {
      setTogglingId(row.id)
      void setDocumentEnabled(workspaceId!, datasetId, row.id, enabled)
        .then(() => invalidate())
        .finally(() => setTogglingId(null))
    },
    [datasetId, invalidate, workspaceId],
  )

  const buildMoreMenu = useCallback(
    (row: DatasetDocument): MenuProps['items'] => {
      const items: MenuProps['items'] = [
        {
          key: 'rename',
          icon: <EditOutlined />,
          label: t('dataset.documents.action.rename'),
          onClick: () => openRename(row),
        },
      ]
      if (row.display_status === 'error') {
        items.push({
          key: 'retry',
          icon: <RedoOutlined />,
          label: t('dataset.documents.action.retry'),
          onClick: () => {
            void retryDocument(workspaceId!, datasetId, row.id).then(() => {
              message.success(t('dataset.documents.retryOk'))
              invalidate()
            })
          },
        })
      }
      items.push({ type: 'divider' })
      items.push({
        key: 'delete',
        icon: <DeleteOutlined />,
        danger: true,
        label: (
          <Popconfirm
            title={t('dataset.documents.deleteConfirm')}
            onConfirm={(event) => {
              event?.stopPropagation()
              void deleteDocument(workspaceId!, datasetId, row.id).then(() => {
                message.success(t('dataset.documents.deleteOk'))
                invalidate()
              })
            }}
            onCancel={(event) => event?.stopPropagation()}
          >
            <span onClick={(event) => event.stopPropagation()}>
              {t('dataset.documents.action.delete')}
            </span>
          </Popconfirm>
        ),
      })
      return items
    },
    [datasetId, invalidate, openRename, t, workspaceId],
  )

  const columns = useMemo<ColumnsType<DatasetDocument>>(
    () => [
      {
        title: '#',
        key: 'index',
        width: 48,
        align: 'center',
        render: (_value, _row, index) => (page - 1) * DEFAULT_PAGE_SIZE + index + 1,
      },
      {
        title: t('dataset.documents.column.name'),
        dataIndex: 'name',
        key: 'name',
        minWidth: 200,
        ellipsis: true,
        render: (name: string, row) => (
          <span className="minerva-document-list-page__name">
            <FileTextOutlined className="minerva-document-list-page__name-icon" />
            <Button
              type="link"
              style={{ padding: 0, height: 'auto' }}
              onClick={() => openSegmentView(row.id)}
            >
              {name}
            </Button>
          </span>
        ),
      },
      {
        title: t('dataset.documents.column.segmentMode'),
        dataIndex: 'doc_form',
        key: 'doc_form',
        width: 104,
        render: (docForm: string) => (
          <Tag bordered className="minerva-document-list-page__segment-tag">
            <UnorderedListOutlined />
            {t(DOC_FORM_I18N[docForm] ?? DOC_FORM_I18N.text_model)}
          </Tag>
        ),
      },
      {
        title: t('dataset.documents.column.characters'),
        dataIndex: 'word_count',
        key: 'word_count',
        width: 96,
        align: 'right',
        render: (value: number | null) => formatCharacterCount(value),
      },
      {
        title: t('dataset.documents.column.hitCount'),
        dataIndex: 'hit_count',
        key: 'hit_count',
        width: 112,
        align: 'right',
        render: (value: number) => value ?? 0,
      },
      {
        title: t('dataset.documents.column.uploadedAt'),
        dataIndex: 'create_at',
        key: 'create_at',
        width: 168,
        render: (value: string | null) => formatUploadedAt(value),
      },
      {
        title: t('dataset.documents.column.status'),
        dataIndex: 'display_status',
        key: 'display_status',
        width: 96,
        render: (status: string) => (
          <span className="minerva-document-list-page__status">
            <span
              className={`minerva-document-list-page__status-dot ${STATUS_DOT_CLASS[status] ?? STATUS_DOT_CLASS.disabled}`}
            />
            {t(`dataset.documents.status.${status}`, { defaultValue: status })}
          </span>
        ),
      },
      {
        title: t('dataset.documents.column.actions'),
        key: 'actions',
        width: 112,
        fixed: 'right',
        render: (_, row) => (
          <span className="minerva-document-list-page__actions">
            <Tooltip
              title={
                row.enabled
                  ? t('dataset.documents.action.disable')
                  : t('dataset.documents.action.enable')
              }
            >
              <Switch
                size="small"
                checked={row.enabled}
                loading={togglingId === row.id}
                onChange={(checked) => toggleEnabled(row, checked)}
                aria-label={
                  row.enabled
                    ? t('dataset.documents.action.disable')
                    : t('dataset.documents.action.enable')
                }
              />
            </Tooltip>
            <Tooltip title={t('dataset.documents.action.segmentList')}>
              <Button
                type="text"
                size="small"
                icon={<UnorderedListOutlined />}
                aria-label={t('dataset.documents.action.segmentList')}
                onClick={() => openSegmentConfig(row.id)}
              />
            </Tooltip>
            <Tooltip title={t('dataset.documents.action.more')}>
              <Dropdown menu={{ items: buildMoreMenu(row) }} trigger={['click']}>
                <Button
                  type="text"
                  size="small"
                  icon={<MoreOutlined />}
                  aria-label={t('dataset.documents.action.more')}
                />
              </Dropdown>
            </Tooltip>
          </span>
        ),
      },
    ],
    [buildMoreMenu, openSegmentConfig, openSegmentView, page, t, toggleEnabled, togglingId],
  )

  const rowSelection = useMemo<TableRowSelection<DatasetDocument>>(
    () => ({
      selectedRowKeys,
      onChange: (keys) => setSelectedRowKeys(keys as string[]),
    }),
    [selectedRowKeys],
  )

  return (
    <>
      <div className="minerva-document-list-page">
        <Card size="small" variant="borderless" className="minerva-document-list-page__card">
          <Form
            form={form}
            layout="inline"
            onFinish={(values) => {
              setPage(1)
              setKeyword(values.keyword?.trim() || undefined)
              setSelectedRowKeys([])
            }}
            className="minerva-document-list-page__filter"
          >
            <Form.Item name="keyword">
              <Input allowClear placeholder={t('dataset.documents.filter.namePh')} style={{ minWidth: 160 }} />
            </Form.Item>
            <Form.Item>
              <Space wrap>
                <Button type="primary" htmlType="submit">
                  {t('rules.search')}
                </Button>
                <Button
                  onClick={() => {
                    form.resetFields()
                    setPage(1)
                    setKeyword(undefined)
                    setSelectedRowKeys([])
                  }}
                >
                  {t('rules.resetFilter')}
                </Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setAppendOpen(true)}>
                  {t('dataset.documents.add')}
                </Button>
                {hasFailedDocs ? (
                  <Button
                    icon={<RedoOutlined />}
                    onClick={() => {
                      void retryFailedDocuments(workspaceId!, datasetId).then((result) => {
                        message.success(
                          t('dataset.documents.retryAllOk', { count: result.retried_count }),
                        )
                        invalidate()
                      })
                    }}
                  >
                    {t('dataset.documents.retryAll')}
                  </Button>
                ) : null}
              </Space>
            </Form.Item>
          </Form>

          <div ref={tableWrapRef} className="minerva-document-list-page__table-wrap">
            <Table<DatasetDocument>
              className="minerva-document-list-page__table minerva-card-table-scroll-ocr"
              rowKey="id"
              loading={listQ.isLoading}
              columns={columns}
              dataSource={listQ.data?.items ?? []}
              rowSelection={rowSelection}
              scroll={{
                x: tableScrollX > 0 ? tableScrollX : 1040,
                y: tableBodyScrollY,
              }}
              sticky
              locale={{ emptyText: t('dataset.documents.empty') }}
              pagination={{
                current: page,
                pageSize: DEFAULT_PAGE_SIZE,
                total: listQ.data?.total ?? 0,
                showSizeChanger: false,
                onChange: (nextPage) => {
                  setPage(nextPage)
                  setSelectedRowKeys([])
                },
              }}
            />
          </div>
        </Card>
      </div>

      <DocumentSegmentModal
        open={Boolean(segmentModal)}
        mode={segmentModal?.mode ?? 'view'}
        datasetId={datasetId}
        documentId={segmentModal?.documentId ?? null}
        onClose={() => setSegmentModal(null)}
      />

      <DatasetCreateWizardModal
        open={appendOpen}
        datasetId={datasetId}
        onClose={() => setAppendOpen(false)}
        onSuccess={() => {
          setAppendOpen(false)
          invalidate()
        }}
      />

      <Modal
        title={t('dataset.documents.renameTitle')}
        open={Boolean(renameDoc)}
        onCancel={() => setRenameDoc(null)}
        onOk={() => {
          void renameForm.validateFields().then((values) => {
            if (!renameDoc) return
            void patchDocument(workspaceId!, datasetId, renameDoc.id, {
              name: values.name.trim(),
            }).then(() => {
              message.success(t('dataset.documents.renameOk'))
              setRenameDoc(null)
              invalidate()
            })
          })
        }}
        destroyOnClose
      >
        <Form form={renameForm} layout="vertical">
          <Form.Item
            name="name"
            label={t('dataset.documents.column.name')}
            rules={[{ required: true, message: t('dataset.create.field.nameRequired') }]}
          >
            <Input allowClear />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
