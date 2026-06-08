/** Document segment list page with CRUD and child chunk expansion. */
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Form, Input, Modal, Popconfirm, Space, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { apiJson } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import {
  getDataset,
  listChildChunks,
  listSegments,
  type DatasetChildChunk,
  type DatasetSegment,
} from '@/features/dataset/api/documents'

function segmentPath(workspaceId: string, datasetId: string, documentId: string, suffix = '') {
  return `/workspaces/${workspaceId}/datasets/${datasetId}/documents/${documentId}${suffix}`
}

/** Shows paginated segments for one document. */
export function DocumentDetailPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const { datasetId = '', documentId = '' } = useParams()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<DatasetSegment | null>(null)
  const [form] = Form.useForm<{ content: string }>()
  const [childMap, setChildMap] = useState<Record<string, DatasetChildChunk[]>>({})
  const [loadingChildId, setLoadingChildId] = useState<string | null>(null)

  const datasetQ = useQuery({
    queryKey: ['dataset-detail', workspaceId, datasetId],
    queryFn: () => getDataset(workspaceId!, datasetId),
    enabled: Boolean(workspaceId && datasetId),
  })

  const chunkStructure = datasetQ.data?.chunk_structure ?? 'text_model'
  const isQa = chunkStructure === 'qa_model'
  const isHierarchical = chunkStructure === 'hierarchical_model'

  const segmentsQ = useQuery({
    queryKey: ['dataset-segments', workspaceId, datasetId, documentId, page, keyword],
    queryFn: () =>
      listSegments(workspaceId!, datasetId, documentId, {
        page,
        page_size: DEFAULT_PAGE_SIZE,
        keyword: keyword.trim() || undefined,
      }),
    enabled: Boolean(workspaceId && datasetId && documentId),
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({
      queryKey: ['dataset-segments', workspaceId, datasetId, documentId],
    })
  }

  const saveM = useMutation({
    mutationFn: async (content: string) => {
      if (editing) {
        return apiJson<DatasetSegment>(
          segmentPath(workspaceId!, datasetId, documentId, `/segments/${editing.id}`),
          {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content }),
          },
        )
      }
      return apiJson<DatasetSegment>(segmentPath(workspaceId!, datasetId, documentId, '/segment'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      })
    },
    onSuccess: () => {
      message.success(t('dataset.segments.saved'))
      setEditorOpen(false)
      setEditing(null)
      form.resetFields()
      invalidate()
    },
    onError: (err: Error) => message.error(err.message),
  })

  const loadChildChunks = async (segmentId: string) => {
    if (childMap[segmentId] || !workspaceId) return
    setLoadingChildId(segmentId)
    try {
      const result = await listChildChunks(workspaceId, datasetId, documentId, segmentId)
      setChildMap((prev) => ({ ...prev, [segmentId]: result.items }))
    } finally {
      setLoadingChildId(null)
    }
  }

  const columns = useMemo<ColumnsType<DatasetSegment>>(
    () => {
      const cols: ColumnsType<DatasetSegment> = [
        { title: '#', dataIndex: 'position', width: 64 },
        {
          title: isQa ? t('dataset.segments.column.question') : t('dataset.segments.column.content'),
          dataIndex: 'content',
          render: (content: string) => (
            <Typography.Paragraph ellipsis={{ rows: 3, expandable: true }} style={{ marginBottom: 0 }}>
              {content}
            </Typography.Paragraph>
          ),
        },
      ]
      if (isQa) {
        cols.push({
          title: t('dataset.segments.column.answer'),
          dataIndex: 'answer',
          width: 220,
          render: (answer: string | null | undefined) => answer ?? '—',
        })
      }
      cols.push(
        { title: t('dataset.segments.column.words'), dataIndex: 'word_count', width: 90 },
        { title: t('dataset.segments.column.hits'), dataIndex: 'hit_count', width: 90 },
      )
      if (isHierarchical) {
        cols.push({
          title: t('dataset.segments.column.children'),
          dataIndex: 'child_count',
          width: 90,
          render: (count: number | undefined) => count ?? 0,
        })
      }
      cols.push({
        title: t('dataset.documents.column.actions'),
        key: 'actions',
        width: 120,
        render: (_, row) => (
          <Space>
            <Button
              type="link"
              size="small"
              onClick={() => {
                setEditing(row)
                form.setFieldsValue({ content: row.content })
                setEditorOpen(true)
              }}
            >
              {t('dataset.segments.edit')}
            </Button>
            <Popconfirm
              title={t('dataset.segments.deleteConfirm')}
              onConfirm={() => {
                void apiJson<null>(
                  segmentPath(workspaceId!, datasetId, documentId, `/segments/${row.id}`),
                  { method: 'DELETE' },
                ).then(() => {
                  message.success(t('dataset.segments.deleted'))
                  invalidate()
                })
              }}
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Space>
        ),
      })
      return cols
    },
    [datasetId, documentId, form, invalidate, isHierarchical, isQa, t, workspaceId],
  )

  return (
    <Card
      title={
        <Space wrap>
          <Link to={`/app/dataset/${datasetId}/documents`}>{t('dataset.segments.backToDocuments')}</Link>
          {chunkStructure !== 'text_model' ? (
            <Tag>
              {t(
                (
                  {
                    text_model: 'dataset.create.docForm.text',
                    hierarchical_model: 'dataset.create.docForm.hierarchical',
                    qa_model: 'dataset.create.docForm.qa',
                  } as const
                )[chunkStructure as 'text_model' | 'hierarchical_model' | 'qa_model'] ??
                  'dataset.create.docForm.text',
              )}
            </Tag>
          ) : null}
        </Space>
      }
      extra={
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            setEditing(null)
            form.resetFields()
            setEditorOpen(true)
          }}
        >
          {t('dataset.segments.add')}
        </Button>
      }
    >
      <Space direction="vertical" style={{ width: '100%', marginBottom: 16 }}>
        <Input.Search
          allowClear
          placeholder={t('dataset.segments.searchPh')}
          onSearch={(value) => {
            setPage(1)
            setKeyword(value)
          }}
        />
      </Space>
      <Table<DatasetSegment>
        rowKey="id"
        loading={segmentsQ.isLoading}
        columns={columns}
        dataSource={segmentsQ.data?.items ?? []}
        locale={{ emptyText: t('dataset.segments.empty') }}
        expandable={
          isHierarchical
            ? {
                expandedRowRender: (row) => {
                  const children = childMap[row.id] ?? []
                  if (loadingChildId === row.id) {
                    return <Typography.Text type="secondary">{t('common.loading')}</Typography.Text>
                  }
                  if (!children.length) {
                    return <Typography.Text type="secondary">{t('dataset.segments.childEmpty')}</Typography.Text>
                  }
                  return (
                    <Space direction="vertical" style={{ width: '100%' }}>
                      {children.map((child) => (
                        <div key={child.id}>
                          <Typography.Text type="secondary">#{child.position}</Typography.Text>
                          <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                            {child.content}
                          </Typography.Paragraph>
                        </div>
                      ))}
                    </Space>
                  )
                },
                onExpand: (expanded, row) => {
                  if (expanded) void loadChildChunks(row.id)
                },
                rowExpandable: (row) => (row.child_count ?? 0) > 0,
              }
            : undefined
        }
        pagination={{
          current: page,
          pageSize: DEFAULT_PAGE_SIZE,
          total: segmentsQ.data?.total ?? 0,
          showSizeChanger: false,
          onChange: setPage,
        }}
      />

      <Modal
        open={editorOpen}
        title={editing ? t('dataset.segments.edit') : t('dataset.segments.add')}
        onCancel={() => setEditorOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={saveM.isPending}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={(values) => saveM.mutate(values.content)}>
          <Form.Item
            name="content"
            label={isQa ? t('dataset.segments.column.question') : t('dataset.segments.column.content')}
            rules={[{ required: true, message: t('dataset.segments.contentRequired') }]}
          >
            <Input.TextArea allowClear rows={8} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
