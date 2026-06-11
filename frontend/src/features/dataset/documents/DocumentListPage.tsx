/** Document list for one knowledge base. */
import {
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlusOutlined,
  RedoOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Form, Input, Modal, Popconfirm, Space, Table, Tag, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
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

const STATUS_COLOR: Record<string, string> = {
  available: 'success',
  indexing: 'processing',
  error: 'error',
  disabled: 'default',
  paused: 'warning',
  archived: 'default',
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

  const openRename = useCallback(
    (row: DatasetDocument) => {
      setRenameDoc(row)
      renameForm.setFieldsValue({ name: row.name })
    },
    [renameForm],
  )

  const columns = useMemo<ColumnsType<DatasetDocument>>(
    () => [
      {
        title: t('dataset.documents.column.name'),
        dataIndex: 'name',
        render: (name: string, row) => (
          <Link to={`/app/dataset/${datasetId}/documents/${row.id}`}>{name}</Link>
        ),
      },
      {
        title: t('dataset.documents.column.status'),
        dataIndex: 'display_status',
        width: 120,
        render: (status: string) => (
          <Tag color={STATUS_COLOR[status] ?? 'default'}>
            {t(`dataset.documents.status.${status}`, { defaultValue: status })}
          </Tag>
        ),
      },
      {
        title: t('dataset.documents.column.words'),
        dataIndex: 'word_count',
        width: 100,
        render: (v: number | null) => v ?? '—',
      },
      {
        title: t('dataset.documents.column.createdAt'),
        dataIndex: 'create_at',
        width: 180,
        render: (v: string | null) => (v ? new Date(v).toLocaleString() : '—'),
      },
      {
        title: t('dataset.documents.column.actions'),
        key: 'actions',
        width: 260,
        render: (_, row) => (
          <Space size="small">
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => openRename(row)}
            />
            <Link to={`/app/dataset/${datasetId}/documents/${row.id}`}>
              <Button type="link" size="small" icon={<EyeOutlined />}>
                {t('dataset.documents.action.segments')}
              </Button>
            </Link>
            {row.display_status === 'error' ? (
              <Button
                type="link"
                size="small"
                icon={<RedoOutlined />}
                onClick={() => {
                  void retryDocument(workspaceId!, datasetId, row.id).then(() => {
                    message.success(t('dataset.documents.retryOk'))
                    invalidate()
                  })
                }}
              >
                {t('dataset.documents.action.retry')}
              </Button>
            ) : null}
            {row.enabled ? (
              <Button
                type="link"
                size="small"
                onClick={() => {
                  void setDocumentEnabled(workspaceId!, datasetId, row.id, false).then(() => invalidate())
                }}
              >
                {t('dataset.documents.action.disable')}
              </Button>
            ) : (
              <Button
                type="link"
                size="small"
                onClick={() => {
                  void setDocumentEnabled(workspaceId!, datasetId, row.id, true).then(() => invalidate())
                }}
              >
                {t('dataset.documents.action.enable')}
              </Button>
            )}
            <Popconfirm
              title={t('dataset.documents.deleteConfirm')}
              onConfirm={() => {
                void deleteDocument(workspaceId!, datasetId, row.id).then(() => {
                  message.success(t('dataset.documents.deleteOk'))
                  invalidate()
                })
              }}
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [datasetId, invalidate, openRename, t, workspaceId],
  )

  return (
    <>
      <Card>
        <Form
          form={form}
          layout="inline"
          onFinish={(values) => {
            setPage(1)
            setKeyword(values.keyword?.trim() || undefined)
          }}
          style={{ marginBottom: 16 }}
        >
          <Form.Item name="keyword">
            <Input allowClear placeholder={t('dataset.documents.filter.namePh')} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                {t('rules.search')}
              </Button>
              <Button
                onClick={() => {
                  form.resetFields()
                  setPage(1)
                  setKeyword(undefined)
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

        <Table<DatasetDocument>
          rowKey="id"
          loading={listQ.isLoading}
          columns={columns}
          dataSource={listQ.data?.items ?? []}
          locale={{ emptyText: t('dataset.documents.empty') }}
          pagination={{
            current: page,
            pageSize: DEFAULT_PAGE_SIZE,
            total: listQ.data?.total ?? 0,
            showSizeChanger: false,
            onChange: setPage,
          }}
        />
      </Card>

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
