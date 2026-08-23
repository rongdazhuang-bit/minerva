/** Graph documents: file upload, plain-text import, index job polling, and list. */

import { DeleteOutlined, InboxOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button,
  Card,
  Empty,
  Form,
  Input,
  Popconfirm,
  Space,
  Table,
  Tag,
  Tooltip,
  Upload,
  message,
} from 'antd'
import type { UploadProps } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { useAuth } from '@/app/AuthContext'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import {
  deleteGraphKbDocument,
  enqueueGraphKbIndex,
  getGraphKb,
  getGraphKbJob,
  importGraphKbPlainText,
  listGraphKbDocuments,
  uploadGraphKbDocument,
  type GraphKbDocumentOut,
} from '@/features/graph-kb/api/graphKb'
import {
  GRAPH_KB_ACTIVE_INDEX_STATUSES,
  GRAPH_KB_UPLOAD_ACCEPT,
  formatSizeBytes,
  indexingStatusColor,
  isGraphKbAllowedExtension,
} from '@/features/graph-kb/shared/graphKbForm'
import './GraphKbDocumentsPage.css'

/** Vertical space reserved below the table body for pagination and chrome. */
const TABLE_SCROLL_GUTTER_PX = 48

type TextImportValues = {
  name: string
  text: string
}

/** Documents tab for `/app/graph-kb/:graphId/documents`. */
export function GraphKbDocumentsPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const { graphId = '' } = useParams()
  const queryClient = useQueryClient()
  const [textForm] = Form.useForm<TextImportValues>()
  const [page, setPage] = useState(1)
  /** Job id returned by POST /index; polled until terminal status. */
  const [jobId, setJobId] = useState<string | null>(null)
  /** Last job id that already produced a terminal toast (avoids StrictMode double fire). */
  const handledJobRef = useRef<string | null>(null)
  const tableWrapRef = useRef<HTMLDivElement | null>(null)
  const [tableBodyScrollY, setTableBodyScrollY] = useState(420)
  const [tableScrollX, setTableScrollX] = useState(0)

  const detailQ = useQuery({
    queryKey: ['graph-kb-detail', workspaceId, graphId],
    queryFn: () => getGraphKb(workspaceId!, graphId),
    enabled: Boolean(workspaceId && graphId),
    refetchInterval: (query) => {
      const status = query.state.data?.indexing_status
      return status && GRAPH_KB_ACTIVE_INDEX_STATUSES.has(status) ? 3000 : false
    },
  })

  const listQ = useQuery({
    queryKey: ['graph-kb-documents', workspaceId, graphId, page],
    queryFn: () => listGraphKbDocuments(workspaceId!, graphId, { page, page_size: DEFAULT_PAGE_SIZE }),
    enabled: Boolean(workspaceId && graphId),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      const graphBusy = detailQ.data?.indexing_status
        ? GRAPH_KB_ACTIVE_INDEX_STATUSES.has(detailQ.data.indexing_status)
        : false
      return graphBusy || items.some((item) => GRAPH_KB_ACTIVE_INDEX_STATUSES.has(item.indexing_status))
        ? 3000
        : false
    },
  })

  const jobQ = useQuery({
    queryKey: ['graph-kb-job', workspaceId, graphId, jobId],
    queryFn: () => getGraphKbJob(workspaceId!, graphId, jobId!),
    enabled: Boolean(workspaceId && graphId && jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && GRAPH_KB_ACTIVE_INDEX_STATUSES.has(status) ? 2000 : false
    },
  })

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['graph-kb-documents', workspaceId, graphId] })
    void queryClient.invalidateQueries({ queryKey: ['graph-kb-detail', workspaceId, graphId] })
    void queryClient.invalidateQueries({ queryKey: ['graph-kbs', workspaceId] })
  }, [graphId, queryClient, workspaceId])

  useEffect(() => {
    const job = jobQ.data
    if (!job || GRAPH_KB_ACTIVE_INDEX_STATUSES.has(job.status)) return
    if (handledJobRef.current === job.id) return
    handledJobRef.current = job.id
    if (job.status === 'completed') {
      message.success(t('graphKb.documents.indexDone'))
    } else if (job.status === 'failed') {
      message.error(job.error || t('graphKb.documents.indexFailed'))
    }
    setJobId(null)
    invalidate()
  }, [invalidate, jobQ.data, t])

  useLayoutEffect(() => {
    const wrap = tableWrapRef.current
    if (wrap == null) return
    const measure = () => {
      const rect = wrap.getBoundingClientRect()
      setTableBodyScrollY(Math.max(160, Math.floor(rect.height - TABLE_SCROLL_GUTTER_PX)))
      setTableScrollX(Math.max(720, Math.floor(rect.width)))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(wrap)
    return () => {
      ro.disconnect()
    }
  }, [listQ.data?.items?.length, page, workspaceId])

  const uploadM = useMutation({
    mutationFn: (file: File) => uploadGraphKbDocument(workspaceId!, graphId, file),
    onSuccess: () => {
      message.success(t('graphKb.documents.uploadOk'))
      invalidate()
    },
    onError: (err: Error) => message.error(err.message),
  })

  const textM = useMutation({
    mutationFn: (values: TextImportValues) =>
      importGraphKbPlainText(workspaceId!, graphId, {
        name: values.name.trim(),
        text: values.text,
      }),
    onSuccess: () => {
      message.success(t('graphKb.documents.textOk'))
      textForm.resetFields()
      invalidate()
    },
    onError: (err: Error) => message.error(err.message),
  })

  const indexM = useMutation({
    mutationFn: () => enqueueGraphKbIndex(workspaceId!, graphId),
    onSuccess: (job) => {
      message.success(t('graphKb.documents.indexStarted'))
      handledJobRef.current = null
      setJobId(job.id)
      invalidate()
    },
    onError: (err: Error) => message.error(err.message),
  })

  const deleteM = useMutation({
    mutationFn: (docId: string) => deleteGraphKbDocument(workspaceId!, graphId, docId),
    onSuccess: (result) => {
      if (result.reindex_enqueued) {
        message.success(result.message || t('graphKb.documents.reindexQueued'))
      } else {
        message.success(t('graphKb.documents.deleteOk'))
      }
      invalidate()
    },
    onError: (err: Error) => message.error(err.message),
  })

  /** Upload one file via XHR client; Ant Design Dragger owns progress UI. */
  const customRequest = useCallback<NonNullable<UploadProps['customRequest']>>(
    async (options) => {
      const raw = options.file as { originFileObj?: File } | File
      const file = raw instanceof File ? raw : (raw.originFileObj as File)
      try {
        const uploaded = await uploadM.mutateAsync(file)
        options.onSuccess?.(uploaded)
      } catch (err) {
        options.onError?.(err instanceof Error ? err : new Error(String(err)))
      }
    },
    [uploadM],
  )

  const columns: ColumnsType<GraphKbDocumentOut> = useMemo(
    () => [
      {
        title: t('graphKb.documents.column.name'),
        dataIndex: 'name',
        key: 'name',
        ellipsis: true,
      },
      {
        title: t('graphKb.documents.column.source'),
        dataIndex: 'source_type',
        key: 'source_type',
        width: 120,
        render: (source: string) => t(`graphKb.documents.source.${source}`, { defaultValue: source }),
      },
      {
        title: t('graphKb.documents.column.size'),
        dataIndex: 'size_bytes',
        key: 'size_bytes',
        width: 100,
        render: (value: number | null) => formatSizeBytes(value),
      },
      {
        title: t('graphKb.documents.column.status'),
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
        title: t('graphKb.documents.column.createdAt'),
        dataIndex: 'create_at',
        key: 'create_at',
        width: 168,
        render: (value: string | null) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '—'),
      },
      {
        title: t('graphKb.documents.column.actions'),
        key: 'actions',
        width: 72,
        render: (_: unknown, row) => (
          <Tooltip title={t('graphKb.documents.delete')}>
            <span>
              <Popconfirm
                title={t('graphKb.documents.deleteConfirm')}
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
                  aria-label={t('graphKb.documents.delete')}
                />
              </Popconfirm>
            </span>
          </Tooltip>
        ),
      },
    ],
    [deleteM, t],
  )

  const graphStatus = detailQ.data?.indexing_status
  const indexBusy =
    indexM.isPending ||
    Boolean(jobId) ||
    Boolean(graphStatus && GRAPH_KB_ACTIVE_INDEX_STATUSES.has(graphStatus))

  if (!workspaceId) {
    return <Empty description={t('settings.ocrNoWorkspace')} style={{ color: 'var(--minerva-ink)' }} />
  }

  return (
    <div className="minerva-graph-kb-documents-page">
      <Card
        size="small"
        variant="borderless"
        className="minerva-graph-kb-documents-page__card minerva-page-shell-card"
      >
        <Space wrap className="minerva-graph-kb-documents-page__toolbar">
          <Button type="primary" loading={indexM.isPending} disabled={indexBusy} onClick={() => indexM.mutate()}>
            {t('graphKb.documents.index')}
          </Button>
          {graphStatus ? (
            <Tag color={indexingStatusColor(graphStatus)}>
              {t(`graphKb.status.${graphStatus}`, { defaultValue: graphStatus })}
            </Tag>
          ) : null}
        </Space>

        <div className="minerva-graph-kb-documents-page__import">
          <Upload.Dragger
            multiple
            accept={GRAPH_KB_UPLOAD_ACCEPT}
            showUploadList={false}
            customRequest={customRequest}
            beforeUpload={(file) => {
              if (!isGraphKbAllowedExtension(file.name)) {
                message.error(t('graphKb.documents.uploadInvalidExt'))
                return Upload.LIST_IGNORE
              }
              return true
            }}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">{t('graphKb.documents.uploadTitle')}</p>
            <p className="ant-upload-hint">{t('graphKb.documents.uploadDesc')}</p>
          </Upload.Dragger>
          <Form
            form={textForm}
            layout="vertical"
            onFinish={(values) => textM.mutate(values)}
          >
            <Form.Item
              name="name"
              label={t('graphKb.documents.textName')}
              rules={[{ required: true, message: t('graphKb.documents.textNameRequired') }]}
            >
              <Input allowClear placeholder={t('graphKb.documents.textNamePh')} />
            </Form.Item>
            <Form.Item
              name="text"
              label={t('graphKb.documents.textBody')}
              rules={[{ required: true, message: t('graphKb.documents.textBodyRequired') }]}
            >
              <Input.TextArea
                allowClear
                rows={4}
                placeholder={t('graphKb.documents.textBodyPh')}
                classNames={{ textarea: 'minerva-scrollbar-thin' }}
              />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={textM.isPending}>
              {t('graphKb.documents.importText')}
            </Button>
          </Form>
        </div>

        <div ref={tableWrapRef} className="minerva-graph-kb-documents-page__table-wrap">
          <Table<GraphKbDocumentOut>
            className="minerva-graph-kb-documents-page__table minerva-card-table-scroll-ocr"
            rowKey="id"
            loading={listQ.isLoading}
            columns={columns}
            dataSource={listQ.data?.items ?? []}
            locale={{ emptyText: t('graphKb.documents.empty') }}
            scroll={{
              x: tableScrollX > 0 ? tableScrollX : 720,
              y: tableBodyScrollY,
            }}
            sticky
            pagination={{
              current: page,
              pageSize: DEFAULT_PAGE_SIZE,
              total: listQ.data?.total ?? 0,
              showSizeChanger: false,
              onChange: (nextPage) => setPage(nextPage),
            }}
          />
        </div>
      </Card>
    </div>
  )
}
