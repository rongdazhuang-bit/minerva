/**
 * 文档翻译主页面：顶部筛选 + 任务表格；上传与段落对照分别为 Modal / 全屏 Modal。
 */
import {
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  FileAddOutlined,
  InboxOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  Empty,
  Modal,
  Popconfirm,
  Progress,
  Select,
  Skeleton,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { UploadProps } from 'antd/es/upload/interface'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { Dayjs } from 'dayjs'
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
} from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ApiError } from '@/api/client'
import {
  createTranslateJob,
  deleteTranslateJob,
  downloadTranslateJob,
  getTranslateJob,
  getTranslateLayoutPages,
  listTranslateJobSegments,
  listTranslateJobs,
  type DocTranslateJobListItem,
  type DocTranslateJobListParams,
} from '@/api/translate'
import { DictText } from '@/components/dict'
import { TranslatePageLayoutCompare } from '@/features/translate/TranslatePageLayoutCompare'
import { MinervaMarkdown } from '@/components/markdown'
import {
  DOC_TRANSLATE_SEGMENT_DONE,
  DOC_TRANSLATE_SEGMENT_FAILED,
  DOC_TRANSLATE_SEGMENT_PENDING,
  DOC_TRANSLATE_STATUS_FAILED,
  DOC_TRANSLATE_STATUS_SUCCESS,
  TRANSLATE_SEGMENT_STATUS_DICT_CODE,
  TRANSLATE_STATUS_DICT_CODE,
} from '@/features/translate/constants'
import { useDictItemTree } from '@/hooks/useDictItemTree'
import { listModelProviders, type ModelProviderListItem } from '@/api/modelProviders'
import { useAuth } from '@/app/AuthContext'
import { useAppMessage } from '@/app/useAppMessage'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import {
  formatTranslateJobDateTime,
  isTranslateJobTerminal,
  shouldShowTranslateDetailPagesSkeleton,
  shouldShowTranslateDetailSegmentsSkeleton,
  translateJobListLabel,
  translateJobStatusTagColor,
} from '@/features/translate/translateJobUi'
import './TranslatePage.css'

const { Text, Title } = Typography

const ACCEPT = '.doc,.docx,.pdf,.txt,.md,.csv,.xls,.xlsx'
const TABLE_SCROLL_GUTTER_PX = 48
/** Popconfirm 关闭后短暂忽略行点击，避免确认钮下方的表格行收到穿透 click 打开详情。 */
const ROW_DETAIL_CLICK_GUARD_MS = 350

/** Render a single-line table cell: column width adapts; overflow is hidden with ellipsis. */
function renderEllipsisTableCell(display: string) {
  const showTip = display.trim() !== '' && display !== '—'
  return (
    <Typography.Text
      className="translate-page__cell-ellipsis"
      ellipsis={showTip ? { tooltip: display } : true}
      style={{ width: '100%', marginBottom: 0 }}
    >
      {display}
    </Typography.Text>
  )
}

/** 详情弹窗标题区骨架（任务元数据加载中）。 */
function TranslateDetailTitleSkeleton() {
  return (
    <div className="translate-page__detail-title-skeleton" aria-hidden>
      <Skeleton.Input active style={{ width: 280, height: 28 }} />
      <Skeleton.Button active size="small" style={{ width: 72 }} />
      <Skeleton.Button active size="small" style={{ width: 120 }} />
      <Skeleton.Button active size="small" style={{ width: 88 }} />
    </div>
  )
}

/** 页面对照 Tab 骨架（版面数据加载中）。 */
function TranslateDetailPagesSkeleton() {
  return (
    <div className="translate-page__detail-pages-skeleton">
      {[0, 1].map((pageIdx) => (
        <section key={pageIdx} className="translate-page__detail-pages-skeleton-page">
          <Skeleton.Input active style={{ width: 100, height: 22, marginBottom: 12 }} />
          <Skeleton.Button active block className="translate-page__detail-pages-skeleton-visual" />
          <div className="translate-page__detail-pages-skeleton-cols">
            <Skeleton active paragraph={{ rows: 5 }} className="translate-page__compare-skeleton" />
            <Skeleton active paragraph={{ rows: 5 }} className="translate-page__compare-skeleton" />
          </div>
        </section>
      ))}
    </div>
  )
}

/** 段落对照 Tab 骨架（段落列表加载中）。 */
function TranslateDetailSegmentsSkeleton() {
  return (
    <div className="translate-page__compare">
      <div className="translate-page__compare-header">
        <Skeleton.Input active size="small" style={{ width: '90%' }} />
        <Skeleton.Input active size="small" style={{ width: '90%' }} />
      </div>
      {Array.from({ length: 4 }, (_, i) => (
        <div key={`seg-sk-${i}`} className="translate-page__compare-pair">
          <Skeleton active paragraph={{ rows: 3 }} className="translate-page__compare-skeleton" />
          <Skeleton active paragraph={{ rows: 3 }} className="translate-page__compare-skeleton" />
        </div>
      ))}
    </div>
  )
}

const LANG_OPTIONS = [
  { value: 'zh-CN', labelKey: 'translate.lang.zhCN' },
  { value: 'en', labelKey: 'translate.lang.en' },
  { value: 'ja', labelKey: 'translate.lang.ja' },
  { value: 'ko', labelKey: 'translate.lang.ko' },
] as const

const TERMINAL = new Set([DOC_TRANSLATE_STATUS_SUCCESS, DOC_TRANSLATE_STATUS_FAILED])

type FilterFormValues = {
  file_name?: string
  status?: string
  create_range?: [Dayjs, Dayjs]
}

/** 工作区文档翻译任务列表页（表格 + 上传/详情弹窗）。 */
export function TranslatePage() {
  const { t } = useTranslation()
  const message = useAppMessage()
  const queryClient = useQueryClient()
  const { workspaceId } = useAuth()
  const [filterForm] = Form.useForm<FilterFormValues>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [filters, setFilters] = useState<DocTranslateJobListParams>({})
  const [uploadOpen, setUploadOpen] = useState(false)
  const [detailJobId, setDetailJobId] = useState<string | null>(null)
  const [detailTab, setDetailTab] = useState<'pages' | 'segments'>('pages')
  /** 每次打开详情弹窗时重置为页面对照 Tab。 */
  useEffect(() => {
    if (detailJobId != null) {
      setDetailTab('pages')
    }
  }, [detailJobId])
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [sourceLang, setSourceLang] = useState<string>('en')
  const [targetLang, setTargetLang] = useState<string>('zh-CN')
  const [modelId, setModelId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  /** 正在调用删除接口的任务 id，用于表格「删除中」遮罩。 */
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null)
  const tableWrapRef = useRef<HTMLDivElement | null>(null)
  /** 时间戳（ms）：此前表格行点击不打开详情 Modal。 */
  const blockRowDetailUntilRef = useRef(0)
  const [tableBodyScrollY, setTableBodyScrollY] = useState(420)
  const [tableScrollX, setTableScrollX] = useState(0)

  const modelsQuery = useQuery({
    queryKey: ['translate-models', workspaceId],
    queryFn: () => listModelProviders(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const translateStatusDictQ = useDictItemTree(TRANSLATE_STATUS_DICT_CODE)

  const translateModels = useMemo(() => {
    const rows = modelsQuery.data ?? []
    return rows.filter(
      (m: ModelProviderListItem) =>
        (Array.isArray(m.tags) ? m.tags : []).includes('TRANSLATE') &&
        m.enabled &&
        Boolean(m.endpoint_url?.trim()) &&
        m.has_api_key,
    )
  }, [modelsQuery.data])

  const listQuery = useQuery({
    queryKey: ['translate-jobs', workspaceId, page, pageSize, filters],
    queryFn: () =>
      listTranslateJobs(workspaceId!, {
        ...filters,
        page,
        page_size: pageSize,
      }),
    enabled: Boolean(workspaceId),
  })

  const jobQuery = useQuery({
    queryKey: ['translate-job', workspaceId, detailJobId],
    queryFn: () => getTranslateJob(workspaceId!, detailJobId!),
    enabled: Boolean(workspaceId && detailJobId),
    refetchInterval: (q) => {
      const st = q.state.data?.status
      if (!st || TERMINAL.has(st)) return false
      return 3000
    },
  })

  const segmentsPageGroupsQuery = useQuery({
    queryKey: ['translate-segments', workspaceId, detailJobId, 'page'],
    queryFn: () => listTranslateJobSegments(workspaceId!, detailJobId!, 'page'),
    enabled: Boolean(workspaceId && detailJobId),
    refetchInterval: () => {
      const st = jobQuery.data?.status
      if (!st || TERMINAL.has(st)) return false
      return 3000
    },
  })

  const layoutPagesQuery = useQuery({
    queryKey: ['translate-layout-pages', workspaceId, detailJobId],
    queryFn: () => getTranslateLayoutPages(workspaceId!, detailJobId!),
    enabled: Boolean(workspaceId && detailJobId),
    refetchInterval: () => {
      const st = jobQuery.data?.status
      if (!st || TERMINAL.has(st)) return false
      return 3000
    },
  })

  const langSelectOptions = useMemo(
    () => LANG_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) })),
    [t],
  )

  const langLabel = useCallback(
    (code: string) => LANG_OPTIONS.find((o) => o.value === code)?.labelKey ?? code,
    [],
  )

  const modelOptions = useMemo(
    () =>
      translateModels.map((m) => ({
        value: m.id,
        label: `${m.provider_name} / ${m.model_name}`,
      })),
    [translateModels],
  )

  const statusFilterOptions = useMemo(
    () =>
      (translateStatusDictQ.data?.flat ?? []).map((item) => ({
        value: item.code,
        label: item.name,
      })),
    [translateStatusDictQ.data?.flat],
  )

  const toFilterParams = useCallback((values: FilterFormValues): DocTranslateJobListParams => {
    const params: DocTranslateJobListParams = {
      file_name: values.file_name?.trim() || undefined,
      status: values.status?.trim() || undefined,
    }
    const range = values.create_range
    if (range != null && range.length === 2) {
      params.create_at_start = range[0].startOf('day').toISOString()
      params.create_at_end = range[1].endOf('day').toISOString()
    }
    return params
  }, [])

  const onSearch = useCallback(
    (values: FilterFormValues) => {
      setPage(1)
      setFilters(toFilterParams(values))
    },
    [toFilterParams],
  )

  const onReset = useCallback(() => {
    filterForm.resetFields()
    setPage(1)
    setFilters({})
  }, [filterForm])

  const handleSubmit = useCallback(async () => {
    if (!workspaceId) {
      message.warning(t('translate.noWorkspace'))
      return
    }
    if (!uploadFile) {
      message.warning(t('translate.pickFile'))
      return
    }
    if (!modelId) {
      message.warning(t('translate.pickModel'))
      return
    }
    setSubmitting(true)
    try {
      const out = await createTranslateJob(workspaceId, {
        file: uploadFile,
        source_lang: sourceLang,
        target_lang: targetLang,
        model_id: modelId,
      })
      setUploadOpen(false)
      setUploadFile(null)
      setDetailJobId(out.id)
      void queryClient.invalidateQueries({ queryKey: ['translate-jobs', workspaceId] })
      message.success(t('translate.jobCreated'))
    } catch (e) {
      message.error(e instanceof Error ? e.message : t('translate.jobCreateFailed'))
    } finally {
      setSubmitting(false)
    }
  }, [
    workspaceId,
    uploadFile,
    modelId,
    sourceLang,
    targetLang,
    message,
    t,
    queryClient,
  ])

  const handleDeleteJob = useCallback(
    async (jobId: string) => {
      if (!workspaceId || deletingJobId != null) return
      setDeletingJobId(jobId)
      blockRowDetailUntilRef.current = Date.now() + ROW_DETAIL_CLICK_GUARD_MS
      try {
        await deleteTranslateJob(workspaceId, jobId)
        if (detailJobId === jobId) setDetailJobId(null)
        void queryClient.invalidateQueries({ queryKey: ['translate-jobs', workspaceId] })
        message.success(t('translate.deleteSuccess'))
      } catch {
        message.error(t('translate.deleteFailed'))
      } finally {
        setDeletingJobId(null)
        blockRowDetailUntilRef.current = Date.now() + ROW_DETAIL_CLICK_GUARD_MS
      }
    },
    [workspaceId, detailJobId, deletingJobId, queryClient, message, t],
  )

  const handleDownloadJob = useCallback(
    async (row: DocTranslateJobListItem) => {
      if (!workspaceId || row.status !== DOC_TRANSLATE_STATUS_SUCCESS) return
      const hide = message.loading(t('translate.downloadPreparing'), 0)
      try {
        const name =
          row.file_name?.trim() ||
          (row.title?.trim() ? `${row.title.trim()}.${row.file_ext}` : `translated.${row.file_ext}`)
        await downloadTranslateJob(workspaceId, row.id, name)
        hide()
        message.success(t('translate.downloadSuccess'))
      } catch (e) {
        hide()
        if (e instanceof ApiError) {
          message.error(e.message)
        } else {
          message.error(e instanceof Error ? e.message : t('translate.downloadFailed'))
        }
      }
    },
    [workspaceId, message, t],
  )

  const blockRowDetailBriefly = useCallback(() => {
    blockRowDetailUntilRef.current = Date.now() + ROW_DETAIL_CLICK_GUARD_MS
  }, [])

  const shouldOpenDetailFromRowClick = useCallback((e: MouseEvent<HTMLElement>) => {
    if (Date.now() < blockRowDetailUntilRef.current) return false
    const el = e.target as HTMLElement
    if (el.closest('.translate-page__table-actions')) return false
    if (el.closest('button, a, .ant-popover, .ant-popconfirm, .ant-dropdown, .ant-select')) {
      return false
    }
    return true
  }, [])

  const uploadProps: UploadProps = {
    maxCount: 1,
    accept: ACCEPT,
    beforeUpload: (file) => {
      setUploadFile(file)
      return false
    },
    onRemove: () => {
      setUploadFile(null)
    },
    fileList: uploadFile
      ? [{ uid: '-1', name: uploadFile.name, status: 'done' as const }]
      : [],
  }

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
  }, [workspaceId, uploadOpen, detailJobId, listQuery.data?.items?.length, pageSize])

  const tableLoading = useMemo(() => {
    if (deletingJobId != null) {
      return { spinning: true, tip: t('translate.deleting') }
    }
    return listQuery.isFetching
  }, [deletingJobId, listQuery.isFetching, t])

  const columns: ColumnsType<DocTranslateJobListItem> = useMemo(
    () => [
      {
        title: t('translate.table.fileName'),
        dataIndex: 'file_name',
        key: 'file_name',
        width: 320,
        fixed: 'left',
        ellipsis: true,
        render: (_v, row) =>
          renderEllipsisTableCell(
            translateJobListLabel(row, t('translate.defaultTitle')),
          ),
      },
      {
        title: t('translate.table.lang'),
        key: 'lang',
        width: 140,
        fixed: 'left',
        ellipsis: true,
        render: (_v, row) =>
          renderEllipsisTableCell(
            `${t(langLabel(row.source_lang))} → ${t(langLabel(row.target_lang))}`,
          ),
      },
      {
        title: t('translate.table.sourceObjectKey'),
        dataIndex: 'source_object_key',
        key: 'source_object_key',
        ellipsis: true,
        render: (v: string) => renderEllipsisTableCell(v?.trim() || '—'),
      },
      {
        title: t('translate.table.resultObjectKey'),
        dataIndex: 'result_object_key',
        key: 'result_object_key',
        ellipsis: true,
        render: (v: string | null) => renderEllipsisTableCell(v?.trim() || '—'),
      },
      {
        title: t('translate.table.segmentTotal'),
        dataIndex: 'segment_total',
        key: 'segment_total',
        width: 88,
        align: 'right',
      },
      {
        title: t('translate.table.segmentDone'),
        dataIndex: 'segment_done',
        key: 'segment_done',
        width: 96,
        align: 'right',
      },
      {
        title: t('translate.table.status'),
        dataIndex: 'status',
        key: 'status',
        width: 96,
        ellipsis: true,
        render: (status: string) => (
          <Tag className="translate-page__status-tag" color={translateJobStatusTagColor(status)}>
            <DictText dictCode={TRANSLATE_STATUS_DICT_CODE} value={status} />
          </Tag>
        ),
      },
      {
        title: t('translate.table.progress'),
        key: 'progress',
        width: 108,
        render: (_v, row) => {
          const percent = row.status === DOC_TRANSLATE_STATUS_SUCCESS ? 100 : row.progress
          return (
            <div className="translate-page__progress-cell">
              <Progress percent={percent} size="small" style={{ margin: 0 }} />
            </div>
          )
        },
      },
      {
        title: t('translate.table.createAt'),
        dataIndex: 'create_at',
        key: 'create_at',
        width: 168,
        ellipsis: true,
        render: (v: string | null) =>
          renderEllipsisTableCell(formatTranslateJobDateTime(v) || '—'),
      },
      {
        title: t('translate.table.updateAt'),
        dataIndex: 'update_at',
        key: 'update_at',
        width: 168,
        ellipsis: true,
        render: (v: string | null) =>
          renderEllipsisTableCell(formatTranslateJobDateTime(v) || '—'),
      },
      {
        title: t('translate.table.actions'),
        key: 'actions',
        width: 108,
        fixed: 'right',
        render: (_v, row) => (
          <Space
            size={4}
            wrap={false}
            className="translate-page__table-actions"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <Tooltip title={t('translate.table.view')}>
              <Button
                type="text"
                size="small"
                icon={<EyeOutlined />}
                aria-label={t('translate.table.view')}
                onClick={(e) => {
                  e.stopPropagation()
                  setDetailJobId(row.id)
                }}
              />
            </Tooltip>
            {row.status === DOC_TRANSLATE_STATUS_SUCCESS ? (
              <Tooltip title={t('translate.download')}>
                <Button
                  type="text"
                  size="small"
                  icon={<DownloadOutlined />}
                  aria-label={t('translate.download')}
                  onClick={(e) => {
                    e.stopPropagation()
                    void handleDownloadJob(row)
                  }}
                />
              </Tooltip>
            ) : null}
            <Popconfirm
              title={t('translate.deleteConfirm')}
              onOpenChange={(open) => {
                if (!open) blockRowDetailBriefly()
              }}
              onConfirm={(e) => {
                e?.stopPropagation()
                blockRowDetailBriefly()
                void handleDeleteJob(row.id)
              }}
              onCancel={(e) => {
                e?.stopPropagation()
                blockRowDetailBriefly()
              }}
            >
              <span
                className="translate-page__table-actions-popconfirm"
                onClick={(e) => e.stopPropagation()}
                onMouseDown={(e) => e.stopPropagation()}
              >
                <Tooltip title={t('translate.deleteJob')}>
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    aria-label={t('translate.deleteJob')}
                  />
                </Tooltip>
              </span>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [t, langLabel, handleDeleteJob, handleDownloadJob, blockRowDetailBriefly],
  )

  const job = jobQuery.data
  const segments = useMemo(
    () => segmentsPageGroupsQuery.data?.groups?.flatMap((g) => g.segments) ?? [],
    [segmentsPageGroupsQuery.data?.groups],
  )
  const showPagesSkeleton = shouldShowTranslateDetailPagesSkeleton(
    job,
    layoutPagesQuery,
    segmentsPageGroupsQuery,
  )
  const showSegmentsSkeleton = shouldShowTranslateDetailSegmentsSkeleton(
    job,
    segmentsPageGroupsQuery,
    segments.length,
  )

  if (!workspaceId) {
    return (
      <div className="translate-page translate-page--table">
        <Alert type="warning" message={t('translate.noWorkspace')} showIcon />
      </div>
    )
  }

  return (
    <>
      <div className="translate-page translate-page--table">
        <Card size="small" variant="borderless" className="translate-page__card">
          <Form form={filterForm} layout="inline" onFinish={onSearch} className="translate-page__filter">
            <Form.Item name="file_name">
              <Input
                allowClear
                placeholder={t('translate.filter.fileName')}
                style={{ minWidth: 160 }}
              />
            </Form.Item>
            <Form.Item name="status">
              <Select
                allowClear
                placeholder={t('translate.filter.status')}
                style={{ minWidth: 140 }}
                options={statusFilterOptions}
              />
            </Form.Item>
            <Form.Item name="create_range">
              <DatePicker.RangePicker
                allowClear
                placeholder={[
                  t('translate.filter.createRangeStart'),
                  t('translate.filter.createRangeEnd'),
                ]}
              />
            </Form.Item>
            <Form.Item>
              <Space>
                <Button htmlType="submit" type="primary">
                  {t('rules.search')}
                </Button>
                <Button onClick={onReset}>{t('rules.resetFilter')}</Button>
                <Button type="dashed" icon={<FileAddOutlined />} onClick={() => setUploadOpen(true)}>
                  {t('translate.newJob')}
                </Button>
              </Space>
            </Form.Item>
          </Form>

          <div ref={tableWrapRef} className="translate-page__table-wrap">
            <Table<DocTranslateJobListItem>
              rowKey="id"
              loading={tableLoading}
              columns={columns}
              dataSource={listQuery.data?.items ?? []}
              pagination={{
                current: page,
                pageSize,
                total: listQuery.data?.total ?? 0,
                showSizeChanger: true,
                pageSizeOptions: [10, 20, 50, 100],
                onChange: (p, ps) => {
                  setPage(p)
                  setPageSize(ps)
                },
              }}
              className="translate-page__table minerva-card-table-scroll-ocr"
              scroll={{ x: tableScrollX > 0 ? tableScrollX : undefined, y: tableBodyScrollY }}
              tableLayout="fixed"
              sticky
              onRow={(row) => ({
                onClick: (e) => {
                  if (!shouldOpenDetailFromRowClick(e)) return
                  setDetailJobId(row.id)
                },
                style: { cursor: 'pointer' },
              })}
            />
          </div>
        </Card>
      </div>

      <Modal
        title={t('translate.uploadModal.title')}
        open={uploadOpen}
        onCancel={() => {
          setUploadOpen(false)
          setUploadFile(null)
        }}
        destroyOnHidden
        footer={null}
        width={560}
      >
        {translateModels.length === 0 && !modelsQuery.isLoading ? (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={t('translate.noModelsConfigured')}
            description={
              <span>
                {t('translate.noModelsHint')}{' '}
                <Link to="/app/settings/models">{t('translate.openModelSettings')}</Link>
              </span>
            }
          />
        ) : null}
        <Form layout="vertical" onFinish={() => void handleSubmit()}>
          <Form.Item>
            <Upload.Dragger {...uploadProps}>
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">{t('translate.uploadHint')}</p>
              <p className="ant-upload-hint">{ACCEPT}</p>
            </Upload.Dragger>
          </Form.Item>
          <Form.Item label={t('translate.sourceLang')}>
            <Select
              value={sourceLang}
              options={langSelectOptions}
              onChange={setSourceLang}
              allowClear={false}
            />
          </Form.Item>
          <Form.Item label={t('translate.targetLang')}>
            <Select
              value={targetLang}
              options={langSelectOptions}
              onChange={setTargetLang}
              allowClear={false}
            />
          </Form.Item>
          <Form.Item label={t('translate.selectModel')}>
            <Select
              value={modelId ?? undefined}
              placeholder={t('translate.pickModel')}
              options={modelOptions}
              onChange={(v) => setModelId(v)}
              allowClear={false}
              loading={modelsQuery.isLoading}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting} block>
            {t('translate.startTranslate')}
          </Button>
        </Form>
      </Modal>

      <Modal
        className="translate-page__detail-modal"
        title={
          jobQuery.isLoading && job == null ? (
            <TranslateDetailTitleSkeleton />
          ) : job ? (
            <div className="translate-page__detail-title">
              <Title level={5} style={{ margin: 0 }}>
                {translateJobListLabel(job, t('translate.defaultTitle'))}
              </Title>
              <Tag color={translateJobStatusTagColor(job.status)}>
                <DictText dictCode={TRANSLATE_STATUS_DICT_CODE} value={job.status} />
              </Tag>
              {!isTranslateJobTerminal(job.status) ? (
                <Progress percent={job.progress} size="small" style={{ width: 120, margin: 0 }} />
              ) : null}
              <Text type="secondary">
                {job.segment_done}/{job.segment_total}
              </Text>
              {job.status === DOC_TRANSLATE_STATUS_SUCCESS ? (
                <Button
                  size="small"
                  icon={<DownloadOutlined />}
                  onClick={() => void handleDownloadJob(job)}
                >
                  {t('translate.download')}
                </Button>
              ) : null}
            </div>
          ) : (
            t('translate.detailModal.title')
          )
        }
        open={detailJobId != null}
        onCancel={() => setDetailJobId(null)}
        footer={null}
        width="100%"
        style={{ top: 0, paddingBottom: 0, maxWidth: '100%' }}
        classNames={{ body: 'minerva-scrollbar-thin translate-page__detail-modal-body' }}
        destroyOnHidden
      >
        {job?.status === DOC_TRANSLATE_STATUS_FAILED && job.error_message ? (
          <Alert type="error" showIcon message={job.error_message} style={{ marginBottom: 16 }} />
        ) : null}
        <Tabs
          className="translate-page__detail-tabs"
          activeKey={detailTab}
          onChange={(k) => setDetailTab(k as 'pages' | 'segments')}
          items={[
            {
              key: 'pages',
              label: t('translate.detailTab.pages', { defaultValue: '页面对照' }),
              children: showPagesSkeleton ? (
                <TranslateDetailPagesSkeleton />
              ) : layoutPagesQuery.isError ? (
                <Alert
                  type="warning"
                  showIcon
                  message={t('translate.detailTab.layoutUnavailable')}
                />
              ) : layoutPagesQuery.data?.pages?.length ? (
                <TranslatePageLayoutCompare
                  pages={layoutPagesQuery.data.pages}
                  groups={segmentsPageGroupsQuery.data?.groups ?? []}
                />
              ) : (
                <Empty description={t('translate.detailTab.noPages')} />
              ),
            },
            {
              key: 'segments',
              label: t('translate.detailTab.segments', { defaultValue: '段落对照' }),
              children: showSegmentsSkeleton ? (
                <TranslateDetailSegmentsSkeleton />
              ) : (
                <div className="translate-page__compare">
                  <div className="translate-page__compare-header">
                    <div className="translate-page__compare-col-title">{t('translate.colSource')}</div>
                    <div className="translate-page__compare-col-title">{t('translate.colTarget')}</div>
                  </div>
                  {segments.map((s) => (
                    <div key={s.id} className="translate-page__compare-pair">
                      <div className="translate-page__segment-row translate-page__segment-row--source">
                        <MinervaMarkdown preset="ocr" markdown={s.source_text} />
                      </div>
                      <div className="translate-page__segment-row translate-page__segment-row--target">
                        {s.translated_text?.trim() ? (
                          <MinervaMarkdown preset="ocr" markdown={s.translated_text} />
                        ) : s.status === DOC_TRANSLATE_SEGMENT_FAILED ? (
                          <Text type="danger">
                            <DictText
                              dictCode={TRANSLATE_SEGMENT_STATUS_DICT_CODE}
                              value={s.status}
                            />
                          </Text>
                        ) : s.status === DOC_TRANSLATE_SEGMENT_DONE ? (
                          <Text type="secondary">{t('translate.segmentMissing')}</Text>
                        ) : (
                          <Text type="secondary">
                            <DictText
                              dictCode={TRANSLATE_SEGMENT_STATUS_DICT_CODE}
                              value={s.status || DOC_TRANSLATE_SEGMENT_PENDING}
                            />
                          </Text>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ),
            },
          ]}
        />
      </Modal>
    </>
  )
}
