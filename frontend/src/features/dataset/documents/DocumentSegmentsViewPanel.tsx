/** Document segment list with Dify-style header and card layout. */
import {
  DeleteOutlined,
  EditOutlined,
  FileTextOutlined,
  PlusOutlined,
  RightOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button,
  Checkbox,
  Empty,
  Form,
  Input,
  Modal,
  Pagination,
  Popconfirm,
  Select,
  Space,
  Switch,
  Typography,
  message,
} from 'antd'
import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { apiJson } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import {
  getDocument,
  listChildChunks,
  listDocuments,
  listSegments,
  setSegmentEnabled,
  type DatasetChildChunk,
  type DatasetSegment,
} from '@/features/dataset/api/documents'
import './DocumentSegmentsViewPanel.css'

const PAGE_SIZE_OPTIONS = [10, 25, 50]

export type DocumentSegmentsViewPanelProps = {
  datasetId: string
  documentId: string
  onDocumentChange: (documentId: string) => void
}

function segmentPath(workspaceId: string, datasetId: string, documentId: string, suffix = '') {
  return `/workspaces/${workspaceId}/datasets/${datasetId}/documents/${documentId}${suffix}`
}

/** Pad segment position for display labels such as `父分段-01`. */
function formatSegmentPosition(position: number): string {
  return String(position).padStart(2, '0')
}

/** Shows paginated segments for one document. */
export function DocumentSegmentsViewPanel({
  datasetId,
  documentId,
  onDocumentChange,
}: DocumentSegmentsViewPanelProps) {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0])
  const [keyword, setKeyword] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<DatasetSegment | null>(null)
  const [form] = Form.useForm<{ content: string }>()
  const [childMap, setChildMap] = useState<Record<string, DatasetChildChunk[]>>({})
  const [expandedChildIds, setExpandedChildIds] = useState<string[]>([])
  const [loadingChildId, setLoadingChildId] = useState<string | null>(null)
  const [togglingSegmentId, setTogglingSegmentId] = useState<string | null>(null)

  const documentQ = useQuery({
    queryKey: ['dataset-document', workspaceId, datasetId, documentId],
    queryFn: () => getDocument(workspaceId!, datasetId, documentId),
    enabled: Boolean(workspaceId && datasetId && documentId),
  })

  const documentsQ = useQuery({
    queryKey: ['dataset-documents-picker', workspaceId, datasetId],
    queryFn: () => listDocuments(workspaceId!, datasetId, { page: 1, page_size: 100 }),
    enabled: Boolean(workspaceId && datasetId),
  })

  const docForm = documentQ.data?.doc_form ?? 'text_model'
  const isQa = docForm === 'qa_model'
  const isHierarchical = docForm === 'hierarchical_model'

  const segmentsQ = useQuery({
    queryKey: ['dataset-segments', workspaceId, datasetId, documentId, page, pageSize, keyword],
    queryFn: () =>
      listSegments(workspaceId!, datasetId, documentId, {
        page,
        page_size: pageSize,
        keyword: keyword.trim() || undefined,
      }),
    enabled: Boolean(workspaceId && datasetId && documentId),
  })

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: ['dataset-segments', workspaceId, datasetId, documentId],
    })
  }, [datasetId, documentId, queryClient, workspaceId])

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

  const documentOptions = useMemo(
    () =>
      (documentsQ.data?.items ?? []).map((doc) => ({
        value: doc.id,
        label: doc.name,
      })),
    [documentsQ.data?.items],
  )

  const segmentTypeLabel = isHierarchical
    ? t('dataset.segments.parentSegmentShort')
    : t('dataset.segments.segmentShort')

  const loadChildChunks = useCallback(
    async (segmentId: string) => {
      if (childMap[segmentId] || !workspaceId) return
      setLoadingChildId(segmentId)
      try {
        const result = await listChildChunks(workspaceId, datasetId, documentId, segmentId)
        setChildMap((prev) => ({ ...prev, [segmentId]: result.items }))
      } finally {
        setLoadingChildId(null)
      }
    },
    [childMap, datasetId, documentId, workspaceId],
  )

  const toggleChildExpand = useCallback(
    (segmentId: string, childCount: number) => {
      if (childCount <= 0) return
      setExpandedChildIds((prev) => {
        const open = prev.includes(segmentId)
        if (!open) void loadChildChunks(segmentId)
        return open ? prev.filter((id) => id !== segmentId) : [...prev, segmentId]
      })
    },
    [loadChildChunks],
  )

  const toggleSegmentEnabled = useCallback(
    (segment: DatasetSegment, enabled: boolean) => {
      setTogglingSegmentId(segment.id)
      void setSegmentEnabled(workspaceId!, datasetId, documentId, segment.id, enabled)
        .then(() => invalidate())
        .finally(() => setTogglingSegmentId(null))
    },
    [datasetId, documentId, invalidate, workspaceId],
  )

  const total = segmentsQ.data?.total ?? 0

  return (
    <div className="minerva-document-detail-page">
      <div className="minerva-document-detail-page__content">
        <div className="minerva-document-detail-page__body">
          <div className="minerva-document-detail-page__toolbar">
            <Select
              className="minerva-document-detail-page__document-select"
              value={documentId}
              loading={documentsQ.isLoading || documentQ.isLoading}
              options={documentOptions}
              showSearch
              optionFilterProp="label"
              suffixIcon={null}
              popupMatchSelectWidth={false}
              onChange={onDocumentChange}
              labelRender={() => (
                <span className="minerva-document-detail-page__document-label">
                  <FileTextOutlined className="minerva-document-detail-page__document-icon" />
                  <span className="minerva-document-detail-page__document-name">
                    {documentQ.data?.name ?? '—'}
                  </span>
                </span>
              )}
            />
            <Space wrap className="minerva-document-detail-page__toolbar-actions">
              <Input.Search
                allowClear
                className="minerva-document-detail-page__search"
                placeholder={t('dataset.segments.searchPh')}
                onSearch={(value) => {
                  setPage(1)
                  setKeyword(value)
                }}
              />
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
            </Space>
          </div>

          <Typography.Text className="minerva-document-detail-page__count">
            {isHierarchical
              ? t('dataset.segments.parentSegmentCount', { count: total })
              : t('dataset.segments.segmentCount', { count: total })}
          </Typography.Text>

          <div
            className={`minerva-document-detail-page__list minerva-scrollbar-styled${
              segmentsQ.isLoading || (segmentsQ.data?.items ?? []).length === 0
                ? ' minerva-document-detail-page__list--centered'
                : ''
            }`}
          >
            {segmentsQ.isLoading ? (
              <Typography.Text type="secondary">{t('common.loading')}</Typography.Text>
            ) : (segmentsQ.data?.items ?? []).length === 0 ? (
              <Empty description={t('dataset.segments.empty')} />
            ) : (
              (segmentsQ.data?.items ?? []).map((segment) => {
                const childExpanded = expandedChildIds.includes(segment.id)
                const children = childMap[segment.id] ?? []
                const childCount = segment.child_count ?? 0
                return (
                  <div key={segment.id} className="minerva-document-detail-page__segment">
                    <div className="minerva-document-detail-page__segment-main">
                      <Checkbox className="minerva-document-detail-page__segment-check" />
                      <div className="minerva-document-detail-page__segment-body">
                        <div className="minerva-document-detail-page__segment-meta">
                          <Typography.Text type="secondary">
                            {segmentTypeLabel}-{formatSegmentPosition(segment.position)} ·{' '}
                            {t('dataset.segments.characterCount', { count: segment.word_count })} ·{' '}
                            {t('dataset.segments.recallCount', { count: segment.hit_count })}
                          </Typography.Text>
                        </div>
                        <Typography.Paragraph className="minerva-document-detail-page__segment-content">
                          {segment.content}
                        </Typography.Paragraph>
                        {isQa && segment.answer ? (
                          <Typography.Paragraph
                            type="secondary"
                            className="minerva-document-detail-page__segment-answer"
                          >
                            {t('dataset.segments.column.answer')}: {segment.answer}
                          </Typography.Paragraph>
                        ) : null}
                        {isHierarchical ? (
                          <button
                            type="button"
                            className="minerva-document-detail-page__child-toggle"
                            onClick={() => toggleChildExpand(segment.id, childCount)}
                          >
                            <RightOutlined
                              className={
                                childExpanded
                                  ? 'minerva-document-detail-page__child-toggle-icon--open'
                                  : undefined
                              }
                            />
                            {t('dataset.segments.childSegmentSummary', { count: childCount })}
                          </button>
                        ) : null}
                        {childExpanded ? (
                          <div className="minerva-document-detail-page__child-list">
                            {loadingChildId === segment.id ? (
                              <Typography.Text type="secondary">{t('common.loading')}</Typography.Text>
                            ) : children.length === 0 ? (
                              <Typography.Text type="secondary">{t('dataset.segments.childEmpty')}</Typography.Text>
                            ) : (
                              children.map((child) => (
                                <div key={child.id} className="minerva-document-detail-page__child-item">
                                  <Typography.Text type="secondary">#{child.position}</Typography.Text>
                                  <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                                    {child.content}
                                  </Typography.Paragraph>
                                </div>
                              ))
                            )}
                          </div>
                        ) : null}
                      </div>
                      <div className="minerva-document-detail-page__segment-actions">
                        <span className="minerva-document-detail-page__segment-status">
                          <span
                            className={`minerva-document-detail-page__status-dot${segment.enabled ? '' : ' minerva-document-detail-page__status-dot--disabled'}`}
                          />
                          {segment.enabled
                            ? t('dataset.segments.enabled')
                            : t('dataset.segments.disabled')}
                        </span>
                        <div className="minerva-document-detail-page__segment-buttons">
                          <Switch
                            size="small"
                            checked={segment.enabled}
                            loading={togglingSegmentId === segment.id}
                            onChange={(checked) => toggleSegmentEnabled(segment, checked)}
                          />
                          <Button
                            type="text"
                            size="small"
                            icon={<EditOutlined />}
                            aria-label={t('dataset.segments.edit')}
                            onClick={() => {
                              setEditing(segment)
                              form.setFieldsValue({ content: segment.content })
                              setEditorOpen(true)
                            }}
                          />
                          <Popconfirm
                            title={t('dataset.segments.deleteConfirm')}
                            onConfirm={() => {
                              void apiJson<null>(
                                segmentPath(workspaceId!, datasetId, documentId, `/segments/${segment.id}`),
                                { method: 'DELETE' },
                              ).then(() => {
                                message.success(t('dataset.segments.deleted'))
                                invalidate()
                              })
                            }}
                          >
                            <Button
                              type="text"
                              size="small"
                              danger
                              icon={<DeleteOutlined />}
                              aria-label={t('dataset.documents.action.delete')}
                            />
                          </Popconfirm>
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })
            )}
          </div>

          <div className="minerva-document-detail-page__footer">
            <Pagination
              current={page}
              pageSize={pageSize}
              total={total}
              showSizeChanger
              pageSizeOptions={PAGE_SIZE_OPTIONS.map(String)}
              onChange={(nextPage, nextSize) => {
                setPage(nextPage)
                setPageSize(nextSize)
              }}
            />
          </div>
        </div>
      </div>

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
    </div>
  )
}
