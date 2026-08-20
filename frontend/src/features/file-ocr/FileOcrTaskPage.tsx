import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  FileAddOutlined,
  HistoryOutlined,
  InboxOutlined,
  LeftOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  MoreOutlined,
  RedoOutlined,
  StopOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Drawer,
  Dropdown,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Progress,
  Result,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Steps,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from 'antd'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { MenuProps } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { UploadFile, UploadProps } from 'antd/es/upload/interface'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { Dayjs } from 'dayjs'
import type { ReactNode } from 'react'
import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/api/client'
import {
  createOcrFiles,
  deleteOcrFile,
  getOcrFileMarkdownPages,
  getOcrLayoutPages,
  type LayoutPagesOut,
  getOcrFileOverviewLogDailyStats,
  getOcrFileOverviewStats,
  listOcrFileLogs,
  listOcrFiles,
  retryOcrFile,
  uploadOcrSourceFile,
  type OcrFileCreateBody,
  type OcrFileListItem,
  type OcrFileListParams,
  type OcrFileLogItem,
  type OcrFileMarkdownPages,
  type OcrFileOverviewLogDailyStatItem,
} from '@/api/ocrTask'
import { useAuth } from '@/app/AuthContext'
import { useAppMessage } from '@/app/useAppMessage'
import type { MessageInstance } from 'antd/es/message/interface'
import { DictText } from '@/components/dict'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import { useCountUp } from '@/hooks/useCountUp'
import { useDictItemTree } from '@/hooks/useDictItemTree'
import mineruLogo from './assets/mineru-logo.png'
import paddleOcrLogo from './assets/paddleocr-logo.jpg'
import { MinervaMarkdown } from '@/components/markdown'
import { LayoutPageViewer } from '@/components/layout/LayoutPageViewer'
import {
  buildOcrMarkdownDocumentForExport,
  sanitizeMarkdownDownloadBasename,
  triggerMarkdownFileDownload,
} from './buildOcrMarkdownExport'
import './FileOcrTaskPage.css'

const MAX_FILE_SIZE = 50 * 1024 * 1024
const MAX_FILE_COUNT = 50
const ALLOWED_EXTS = new Set(['pdf', 'jpg', 'jpeg', 'png'])
const OCR_TYPE_DICT_CODE = 'TOOL_OCR'

/** Space for table header row, pagination bar, and borders when deriving ``scroll.y`` from the flex pane. */
const FILE_OCR_TASK_TABLE_SCROLL_GUTTER_PX = 112

/** Sum of column ``width`` values so ``scroll.x`` keeps a stable layout (long names ellipsize instead of stretching). */
const FILE_OCR_TASK_TABLE_SCROLL_X =
  200 + 120 + 132 + 240 + 88 + 112 + 172 + 172 + 100

/** Coerce API row fields so charts stay numeric even if JSON shape drifts. */
function normalizeOcrLogDailyChartRow(r: OcrFileOverviewLogDailyStatItem): {
  date: string
  paddle_success: number
  paddle_failed: number
  mineru_success: number
  mineru_failed: number
} {
  const n = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
  return {
    date: r.date,
    paddle_success: n(r.paddle_success),
    paddle_failed: n(r.paddle_failed),
    mineru_success: n(r.mineru_success),
    mineru_failed: n(r.mineru_failed),
  }
}

/**
 * Renders a single-line table cell: fixed width column + ellipsis; hover shows full text when not a placeholder dash.
 */
function renderEllipsisTableCell(display: string) {
  const showTip = display.trim() !== '' && display !== '—'
  return (
    <Typography.Text
      className="minerva-file-ocr-tasks__cell-ellipsis"
      ellipsis={showTip ? { tooltip: display } : true}
      style={{ width: '100%', marginBottom: 0 }}
    >
      {display}
    </Typography.Text>
  )
}

type OcrTypeValue = 'PADDLE_OCR' | 'MINERU'
type OcrTypeOption = { value: OcrTypeValue; label: string; description: string; icon: ReactNode }
type FilterFormValues = {
  file_name?: string
  ocr_type?: string
  status?: string
  create_range?: [Dayjs, Dayjs]
}

/** Normalize date-time string into locale text. */
function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString(undefined, { hour12: false }) : '—'
}

/** Convert byte size to MB text for table display. */
function formatFileSize(value: number | null | undefined) {
  if (value == null) return '—'
  return `${(value / 1024 / 1024).toFixed(2)} MB`
}

/** Extract lower-case extension from file name. */
function fileExt(fileName: string) {
  const idx = fileName.lastIndexOf('.')
  if (idx < 0) return ''
  return fileName.slice(idx + 1).toLowerCase()
}

/** Validate one source file against extension and size constraints. */
function validateSourceFile(
  file: File,
  t: (key: string) => string,
  messageApi: MessageInstance,
) {
  const ext = fileExt(file.name)
  if (!ALLOWED_EXTS.has(ext)) {
    void messageApi.error(t('fileOcr.tasks.upload.invalidExt'))
    return false
  }
  if (file.size > MAX_FILE_SIZE) {
    void messageApi.error(t('fileOcr.tasks.upload.tooLarge'))
    return false
  }
  return true
}

/** Build Steps rows with titles only (no per-node subtitles under the wizard). */
function buildWizardStepItems(t: (key: string) => string) {
  return [
    { title: t('fileOcr.tasks.wizard.stepSelectTool') },
    { title: t('fileOcr.tasks.wizard.stepSelectFiles') },
    { title: t('fileOcr.tasks.wizard.stepUpload') },
    { title: t('fileOcr.tasks.wizard.stepDone') },
  ]
}

/** Keeps OCR type cards configuration in one place. */
function buildOcrTypeOptions(t: (key: string) => string): OcrTypeOption[] {
  return [
    {
      value: 'PADDLE_OCR',
      label: 'PaddleOCR',
      description: t('fileOcr.tasks.wizard.ocrTypePaddleDesc'),
      icon: (
        <img
          src={paddleOcrLogo}
          alt=""
          className="minerva-file-ocr-tasks__ocr-type-logo"
          decoding="async"
          aria-hidden
        />
      ),
    },
    {
      value: 'MINERU',
      label: 'MinerU',
      description: t('fileOcr.tasks.wizard.ocrTypeMinerDesc'),
      icon: (
        <img
          src={mineruLogo}
          alt=""
          className="minerva-file-ocr-tasks__ocr-type-logo"
          decoding="async"
          aria-hidden
        />
      ),
    },
  ]
}

export function RulesFileOcrOverviewPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const chartBoxRef = useRef<HTMLDivElement | null>(null)
  const [chartBoxW, setChartBoxW] = useState(0)
  const statsQuery = useQuery({
    queryKey: ['ocrFileOverviewStats', workspaceId],
    queryFn: () => getOcrFileOverviewStats(workspaceId!),
    enabled: Boolean(workspaceId),
  })
  const dailyStatsQuery = useQuery({
    queryKey: ['ocrFileOverviewLogDailyStats', workspaceId],
    queryFn: () => getOcrFileOverviewLogDailyStats(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const pending = statsQuery.isPending
  const err = statsQuery.error
  const stats = statsQuery.data

  const chartPending = dailyStatsQuery.isPending
  const dailyErr = dailyStatsQuery.error
  const dailyStats = dailyStatsQuery.data

  const chartData = useMemo(() => {
    const raw = dailyStats?.items
    if (raw == null || raw.length === 0) return []
    return raw.map((row) => normalizeOcrLogDailyChartRow(row))
  }, [dailyStats])

  useLayoutEffect(() => {
    if (chartData.length === 0) {
      setChartBoxW(0)
      return
    }
    const el = chartBoxRef.current
    if (el == null) return
    const measure = () => {
      const w = Math.floor(el.getBoundingClientRect().width)
      setChartBoxW(w > 0 ? w : 0)
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => {
      ro.disconnect()
    }
  }, [workspaceId, stats, chartData.length])

  const hasStats = Boolean(stats)
  const displayInit = useCountUp(stats?.init_count ?? 0, { enabled: hasStats })
  const displayProcess = useCountUp(stats?.process_count ?? 0, { enabled: hasStats })
  const displaySuccess = useCountUp(stats?.success_count ?? 0, { enabled: hasStats })
  const displayFailed = useCountUp(stats?.failed_count ?? 0, { enabled: hasStats })

  return (
    <div className="minerva-file-ocr-overview minerva-page-fill">
      {err != null && (
        <Alert
          type="error"
          showIcon
          message={err instanceof ApiError ? err.message : t('common.error')}
          style={{ marginBottom: 16 }}
        />
      )}
      <Spin spinning={pending}>
        {stats == null ? (
          <Empty description={t('placeholders.rulesFileOcr')} style={{ color: 'var(--minerva-ink)' }} />
        ) : (
          <>
            <div className="minerva-file-ocr-overview__stats-scroll">
              <Row wrap={false} gutter={[18, 0]} className="minerva-file-ocr-overview__stats">
                <Col flex="1 1 0" className="minerva-file-ocr-overview__stat-col">
                  <Card
                    size="small"
                    className="minerva-file-ocr-overview__card minerva-file-ocr-overview__card--init"
                    variant="borderless"
                  >
                    <Statistic
                      title={t('fileOcr.overview.kpiInit')}
                      value={displayInit}
                      prefix={<ClockCircleOutlined className="minerva-file-ocr-overview__icon" aria-hidden />}
                    />
                  </Card>
                </Col>
                <Col flex="1 1 0" className="minerva-file-ocr-overview__stat-col">
                  <Card
                    size="small"
                    className="minerva-file-ocr-overview__card minerva-file-ocr-overview__card--process"
                    variant="borderless"
                  >
                    <Statistic
                      title={t('fileOcr.overview.kpiProcess')}
                      value={displayProcess}
                      prefix={<LoadingOutlined className="minerva-file-ocr-overview__icon" aria-hidden />}
                    />
                  </Card>
                </Col>
                <Col flex="1 1 0" className="minerva-file-ocr-overview__stat-col">
                  <Card
                    size="small"
                    className="minerva-file-ocr-overview__card minerva-file-ocr-overview__card--success"
                    variant="borderless"
                  >
                    <Statistic
                      title={t('fileOcr.overview.kpiSuccess')}
                      value={displaySuccess}
                      prefix={<CheckCircleOutlined className="minerva-file-ocr-overview__icon" aria-hidden />}
                    />
                  </Card>
                </Col>
                <Col flex="1 1 0" className="minerva-file-ocr-overview__stat-col">
                  <Card
                    size="small"
                    className="minerva-file-ocr-overview__card minerva-file-ocr-overview__card--failed"
                    variant="borderless"
                  >
                    <Statistic
                      title={t('fileOcr.overview.kpiFailed')}
                      value={displayFailed}
                      prefix={<CloseCircleOutlined className="minerva-file-ocr-overview__icon" aria-hidden />}
                    />
                  </Card>
                </Col>
              </Row>
            </div>
            <Card
              size="small"
              variant="borderless"
              className="minerva-file-ocr-overview__chart-card"
              title={t('fileOcr.overview.logDailyChartTitle')}
            >
              {dailyErr != null && (
                <Alert
                  type="warning"
                  showIcon
                  message={dailyErr instanceof ApiError ? dailyErr.message : t('common.error')}
                  style={{ marginBottom: 12 }}
                />
              )}
              <Spin spinning={chartPending}>
                {!chartPending && dailyErr == null && chartData.length > 0 && (
                  <div ref={chartBoxRef} className="minerva-file-ocr-overview__chart-wrap">
                    {chartBoxW > 0 ? (
                      <LineChart
                        width={chartBoxW}
                        height={320}
                        data={chartData}
                        margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--minerva-border, #2a3f58)" opacity={0.45} />
                        <XAxis
                          dataKey="date"
                          tickFormatter={(v) => (typeof v === 'string' && v.length >= 10 ? v.slice(5) : String(v))}
                          tick={{ fill: 'var(--minerva-ink-muted, #94a3b8)', fontSize: 11 }}
                        />
                        <YAxis
                          width={44}
                          allowDecimals={false}
                          tick={{ fill: 'var(--minerva-ink-muted, #94a3b8)', fontSize: 11 }}
                        />
                        <RechartsTooltip
                          contentStyle={{
                            background: 'var(--minerva-surface, #1a2836)',
                            borderColor: 'var(--minerva-border, #2a3f58)',
                          }}
                        />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        <Line
                          type="monotone"
                          dataKey="paddle_success"
                          name={t('fileOcr.overview.seriesPaddleSuccess')}
                          stroke="#22c55e"
                          strokeWidth={2}
                          dot={false}
                          isAnimationActive={false}
                        />
                        <Line
                          type="monotone"
                          dataKey="paddle_failed"
                          name={t('fileOcr.overview.seriesPaddleFailed')}
                          stroke="#ef4444"
                          strokeWidth={2}
                          dot={false}
                          isAnimationActive={false}
                        />
                        <Line
                          type="monotone"
                          dataKey="mineru_success"
                          name={t('fileOcr.overview.seriesMineruSuccess')}
                          stroke="#38bdf8"
                          strokeWidth={2}
                          dot={false}
                          isAnimationActive={false}
                        />
                        <Line
                          type="monotone"
                          dataKey="mineru_failed"
                          name={t('fileOcr.overview.seriesMineruFailed')}
                          stroke="#f97316"
                          strokeWidth={2}
                          dot={false}
                          isAnimationActive={false}
                        />
                      </LineChart>
                    ) : (
                      <div className="minerva-file-ocr-overview__chart-measure" aria-hidden />
                    )}
                  </div>
                )}
                {!chartPending && dailyErr == null && chartData.length === 0 && (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={t('fileOcr.overview.logDailyChartEmpty')}
                    style={{ margin: '24px 0' }}
                  />
                )}
              </Spin>
            </Card>
          </>
        )}
      </Spin>
    </div>
  )
}

/** Lists OCR tasks and hosts the modal wizard used to enqueue new OCR uploads. */
export function RulesFileOcrTaskPage() {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const queryClient = useQueryClient()
  const { workspaceId } = useAuth()
  const [filterForm] = Form.useForm<FilterFormValues>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [filters, setFilters] = useState<OcrFileListParams>({})
  const [wizardOpen, setWizardOpen] = useState(false)
  /** Wizard pane index: OCR tool, file picker, upload run, or success. */
  const [wizardStep, setWizardStep] = useState<1 | 2 | 3 | 4>(1)
  const [ocrType, setOcrType] = useState<OcrTypeValue | null>(null)
  const [uploadList, setUploadList] = useState<UploadFile[]>([])
  const [progressMap, setProgressMap] = useState<Record<string, number>>({})
  /** Tracks which queue items failed S3/source upload during the wizard submit loop. */
  const [uploadFailedByUid, setUploadFailedByUid] = useState<Record<string, boolean>>({})
  const [submitting, setSubmitting] = useState(false)
  /** Task count shown on the post-upload success pane; cleared when reopening the wizard. */
  const [createdTaskCount, setCreatedTaskCount] = useState<number | null>(null)
  const [refreshTick, setRefreshTick] = useState(0)
  /** OCR run log drawer: which task is selected and whether the drawer is visible. */
  const [logDrawerOpen, setLogDrawerOpen] = useState(false)
  const [logTarget, setLogTarget] = useState<{ id: string; file_name: string | null } | null>(null)
  const [logPage, setLogPage] = useState(1)
  /** Markdown detail drawer for SUCCESS tasks (per-page OCR output). */
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false)
  const [detailTarget, setDetailTarget] = useState<OcrFileListItem | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailData, setDetailData] = useState<OcrFileMarkdownPages | null>(null)
  const [detailLayoutData, setDetailLayoutData] = useState<LayoutPagesOut | null>(null)
  const [detailTab, setDetailTab] = useState<'layout' | 'markdown'>('layout')
  const detailAbortRef = useRef<AbortController | null>(null)
  const tableWrapRef = useRef<HTMLDivElement | null>(null)
  const [tableBodyScrollY, setTableBodyScrollY] = useState(420)
  const ocrTypeOptions = useMemo(() => buildOcrTypeOptions(t), [t])
  const wizardSteps = useMemo(() => buildWizardStepItems(t), [t])
  const ocrTypeDictQ = useDictItemTree(OCR_TYPE_DICT_CODE)
  const ocrTypeFilterOptions = useMemo(() => {
    const dictOptions = (ocrTypeDictQ.data?.flat ?? []).map((item) => ({
      value: item.code,
      label: item.name,
    }))
    if (dictOptions.length > 0) return dictOptions
    return [
      { value: 'PADDLE_OCR', label: 'PaddleOCR' },
      { value: 'MINERU', label: 'MinerU' },
    ]
  }, [ocrTypeDictQ.data?.flat])
  const listQuery = useQuery({
    queryKey: ['ocrFileTaskList', workspaceId, page, pageSize, filters, refreshTick],
    queryFn: () =>
      listOcrFiles(workspaceId!, {
        ...filters,
        page,
        page_size: pageSize,
      }),
    enabled: Boolean(workspaceId),
  })

  const logQuery = useQuery({
    queryKey: ['ocrFileLogs', workspaceId, logTarget?.id, logPage],
    queryFn: () =>
      listOcrFileLogs(workspaceId!, logTarget!.id, {
        page: logPage,
        page_size: DEFAULT_PAGE_SIZE,
      }),
    enabled: logDrawerOpen && Boolean(workspaceId) && Boolean(logTarget?.id),
  })

  useLayoutEffect(() => {
    const wrap = tableWrapRef.current
    if (wrap == null) return
    const measure = () => {
      const h = wrap.getBoundingClientRect().height
      setTableBodyScrollY(Math.max(160, Math.floor(h - FILE_OCR_TASK_TABLE_SCROLL_GUTTER_PX)))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(wrap)
    return () => {
      ro.disconnect()
    }
  }, [workspaceId, wizardOpen, listQuery.data?.items?.length, listQuery.error, pageSize])

  /** Convert status code into localized text. */
  const statusText = useCallback(
    (status: string) => {
      if (status === 'INIT') return t('fileOcr.tasks.status.INIT')
      if (status === 'PROCESS') return t('fileOcr.tasks.status.PROCESS')
      if (status === 'SUCCESS') return t('fileOcr.tasks.status.SUCCESS')
      if (status === 'FAILED') return t('fileOcr.tasks.status.FAILED')
      return status
    },
    [t],
  )

  /** Convert status code into tag color token. */
  const statusColor = useCallback((status: string) => {
    if (status === 'SUCCESS') return 'success'
    if (status === 'FAILED') return 'error'
    if (status === 'PROCESS') return 'processing'
    return 'default'
  }, [])

  /** Build one disabled placeholder action callback. */
  const onPendingAction = useCallback((nameKey: string) => {
    void messageApi.info(t('fileOcr.tasks.actionPending', { action: t(nameKey) }))
  }, [t])

  /** Delete one task row and refresh list plus overview KPI cache. */
  const handleDeleteOcrTask = useCallback(
    async (ocrFileId: string) => {
      if (!workspaceId) return
      try {
        await deleteOcrFile(workspaceId, ocrFileId)
        void messageApi.success(t('fileOcr.tasks.deleteSuccess'))
        void queryClient.invalidateQueries({ queryKey: ['ocrFileOverviewStats', workspaceId] })
        setRefreshTick((n) => n + 1)
      } catch (e) {
        if (e instanceof ApiError) void messageApi.error(e.message)
        else void messageApi.error(t('common.error'))
      }
    },
    [queryClient, t, workspaceId],
  )

  /** Re-queue one OCR task for the worker by resetting its status to INIT. */
  const handleRetryOcrTask = useCallback(
    async (ocrFileId: string) => {
      if (!workspaceId) return
      try {
        await retryOcrFile(workspaceId, ocrFileId)
        void messageApi.success(t('fileOcr.tasks.retrySuccess'))
        void queryClient.invalidateQueries({ queryKey: ['ocrFileOverviewStats', workspaceId] })
        setRefreshTick((n) => n + 1)
      } catch (e) {
        if (e instanceof ApiError) void messageApi.error(e.message)
        else void messageApi.error(t('common.error'))
      }
    },
    [queryClient, t, workspaceId],
  )

  /** Open the run-log drawer for one task row and reset pagination to the first page. */
  const openLogDrawer = useCallback((row: OcrFileListItem) => {
    setLogTarget({ id: row.id, file_name: row.file_name ?? null })
    setLogPage(1)
    setLogDrawerOpen(true)
  }, [])

  /** Close markdown detail drawer and cancel in-flight fetch. */
  const closeDetailDrawer = useCallback(() => {
    detailAbortRef.current?.abort()
    detailAbortRef.current = null
    setDetailDrawerOpen(false)
    setDetailTarget(null)
    setDetailData(null)
    setDetailLayoutData(null)
    setDetailError(null)
    setDetailLoading(false)
    setDetailTab('layout')
  }, [])

  /** Fetch markdown pages and save one ``.md`` file with inlined images (same pipeline as the detail drawer). */
  const handleDownloadOcrMarkdown = useCallback(
    async (row: OcrFileListItem) => {
      if (row.status !== 'SUCCESS' || workspaceId == null) return
      const hideLoading = messageApi.loading(t('fileOcr.tasks.downloadPreparing'), 0)
      try {
        const data = await getOcrFileMarkdownPages(workspaceId, row.id)
        const docTitle = row.file_name?.trim() || t('fileOcr.tasks.detail.titleFallback')
        const body = buildOcrMarkdownDocumentForExport(data, {
          documentTitle: docTitle,
          pageTitle: (n) => t('fileOcr.tasks.detail.pageTitle', { n }),
          pageEmpty: t('fileOcr.tasks.detail.pageEmpty'),
        })
        const base = sanitizeMarkdownDownloadBasename(row.file_name?.trim() || 'ocr-result')
        triggerMarkdownFileDownload(body, `${base}.md`)
        hideLoading()
        void messageApi.success(t('fileOcr.tasks.downloadSuccess'))
      } catch (e) {
        hideLoading()
        if (e instanceof ApiError) {
          if (e.code === 'ocr_file.detail_requires_success') {
            void messageApi.error(t('fileOcr.tasks.detail.err409'))
          } else if (e.code === 'ocr_file.unsupported_detail_type') {
            void messageApi.error(t('fileOcr.tasks.detail.err422'))
          } else {
            void messageApi.error(e.message)
          }
        } else {
          void messageApi.error(t('common.error'))
        }
      }
    },
    [t, workspaceId],
  )

  /** Open markdown detail drawer and load pages for a SUCCESS task. */
  const openDetailDrawer = useCallback(
    async (row: OcrFileListItem) => {
      if (row.status !== 'SUCCESS' || workspaceId == null) return
      detailAbortRef.current?.abort()
      const ac = new AbortController()
      detailAbortRef.current = ac
      setDetailTarget(row)
      setDetailDrawerOpen(true)
      setDetailError(null)
      setDetailData(null)
      setDetailLayoutData(null)
      setDetailLoading(true)
      try {
        const [layoutRes, mdRes] = await Promise.allSettled([
          getOcrLayoutPages(workspaceId, row.id),
          getOcrFileMarkdownPages(workspaceId, row.id, { signal: ac.signal }),
        ])
        if (mdRes.status === 'fulfilled') {
          setDetailData(mdRes.value)
        }
        if (layoutRes.status === 'fulfilled') {
          setDetailLayoutData(layoutRes.value)
        } else if (mdRes.status !== 'fulfilled') {
          throw mdRes.reason
        }
      } catch (e) {
        const isAbort =
          (e instanceof DOMException && e.name === 'AbortError') ||
          (e instanceof Error && e.name === 'AbortError')
        if (isAbort) {
          return
        }
        if (e instanceof ApiError) {
          if (e.code === 'ocr_file.detail_requires_success') {
            setDetailError(t('fileOcr.tasks.detail.err409'))
          } else if (e.code === 'ocr_file.unsupported_detail_type') {
            setDetailError(t('fileOcr.tasks.detail.err422'))
          } else {
            setDetailError(e.message)
          }
        } else {
          setDetailError(t('common.error'))
        }
      } finally {
        if (!ac.signal.aborted) {
          setDetailLoading(false)
        }
      }
    },
    [t, workspaceId],
  )

  const logColumns: ColumnsType<OcrFileLogItem> = useMemo(
    () => [
      {
        title: t('fileOcr.tasks.logCol.createAt'),
        dataIndex: 'create_at',
        key: 'create_at',
        width: 180,
        render: (v: string) => formatDateTime(v),
      },
      {
        title: t('fileOcr.tasks.logCol.updateAt'),
        dataIndex: 'update_at',
        key: 'update_at',
        width: 180,
        render: (v: string | null) => formatDateTime(v),
      },
      {
        title: t('fileOcr.tasks.logCol.status'),
        dataIndex: 'status',
        key: 'status',
        width: 120,
        render: (v: string) => {
          const label =
            v === 'RUNNING'
              ? t('fileOcr.tasks.logStatus.RUNNING')
              : v === 'SUCCESS'
                ? t('fileOcr.tasks.logStatus.SUCCESS')
                : v === 'FAILED'
                  ? t('fileOcr.tasks.logStatus.FAILED')
                  : v
          const color =
            v === 'SUCCESS' ? 'success' : v === 'FAILED' ? 'error' : v === 'RUNNING' ? 'processing' : 'default'
          return <Tag color={color}>{label}</Tag>
        },
      },
      {
        title: t('fileOcr.tasks.logCol.remark'),
        dataIndex: 'remark',
        key: 'remark',
        ellipsis: true,
        render: (v: string | null) => v?.trim() || '—',
      },
    ],
    [t],
  )

  const columns: ColumnsType<OcrFileListItem> = useMemo(
    () => [
      {
        title: t('fileOcr.tasks.col.fileName'),
        dataIndex: 'file_name',
        key: 'file_name',
        width: 200,
        render: (v: string | null) => renderEllipsisTableCell(v?.trim() || '—'),
      },
      {
        title: t('fileOcr.tasks.col.ocrType'),
        dataIndex: 'ocr_type',
        key: 'ocr_type',
        width: 120,
        render: (v: string | null) => <DictText dictCode={OCR_TYPE_DICT_CODE} value={v} />,
      },
      {
        title: t('fileOcr.tasks.col.fileSize'),
        dataIndex: 'file_size',
        key: 'file_size',
        width: 132,
        render: (v: number | null) => formatFileSize(v),
      },
      {
        title: t('fileOcr.tasks.col.objectKey'),
        dataIndex: 'object_key',
        key: 'object_key',
        width: 240,
        render: (v: string) => renderEllipsisTableCell(v?.trim() || '—'),
      },
      {
        title: t('fileOcr.tasks.col.pageCount'),
        dataIndex: 'page_count',
        key: 'page_count',
        width: 88,
        render: (v: number | null) => (v == null ? '—' : v),
      },
      {
        title: t('fileOcr.tasks.col.status'),
        dataIndex: 'status',
        key: 'status',
        width: 112,
        render: (v: string) => <Tag color={statusColor(v)}>{statusText(v)}</Tag>,
      },
      {
        title: t('fileOcr.tasks.col.createAt'),
        dataIndex: 'create_at',
        key: 'create_at',
        width: 172,
        render: (v: string | null) => formatDateTime(v),
      },
      {
        title: t('fileOcr.tasks.col.updateAt'),
        dataIndex: 'update_at',
        key: 'update_at',
        width: 172,
        render: (v: string | null) => formatDateTime(v),
      },
      {
        title: t('fileOcr.tasks.col.actions'),
        key: 'actions',
        width: 100,
        fixed: 'right',
        render: (_, row) => {
          const moreMenuItems: MenuProps['items'] = [
            {
              key: 'runLogs',
              icon: <HistoryOutlined />,
              label: t('fileOcr.tasks.action.runLogs'),
              onClick: () => openLogDrawer(row),
            },
            {
              key: 'retry',
              icon: <RedoOutlined />,
              label: t('fileOcr.tasks.action.retry'),
              disabled: row.status === 'INIT' || row.status === 'PROCESS',
              onClick: () => {
                if (row.status === 'INIT' || row.status === 'PROCESS') return
                void handleRetryOcrTask(row.id)
              },
            },
            {
              key: 'download',
              icon: <DownloadOutlined />,
              label: t('fileOcr.tasks.action.download'),
              disabled: row.status !== 'SUCCESS',
              onClick: () => {
                if (row.status !== 'SUCCESS') return
                void handleDownloadOcrMarkdown(row)
              },
            },
            {
              key: 'cancel',
              icon: <StopOutlined />,
              label: t('fileOcr.tasks.action.cancel'),
              disabled: row.status !== 'PROCESS',
              onClick: () => {
                if (row.status !== 'PROCESS') return
                onPendingAction('fileOcr.tasks.action.cancel')
              },
            },
            { type: 'divider' },
            {
              key: 'delete',
              danger: true,
              icon: <DeleteOutlined />,
              label: (
                <Popconfirm
                  title={t('fileOcr.tasks.deleteConfirm')}
                  okText={t('common.yes')}
                  cancelText={t('common.cancel')}
                  okButtonProps={{ danger: true }}
                  onConfirm={() => void handleDeleteOcrTask(row.id)}
                  onCancel={(e) => e?.stopPropagation()}
                >
                  <span onClick={(e) => e.stopPropagation()}>
                    {t('fileOcr.tasks.action.delete')}
                  </span>
                </Popconfirm>
              ),
            },
          ]
          return (
            <Space size={4} wrap={false}>
              <Tooltip
                title={
                  row.status === 'SUCCESS'
                    ? t('fileOcr.tasks.action.view')
                    : t('fileOcr.tasks.action.viewDisabledHint')
                }
              >
                <Button
                  type="text"
                  size="small"
                  icon={<EyeOutlined />}
                  disabled={row.status !== 'SUCCESS'}
                  onClick={() => {
                    if (row.status !== 'SUCCESS') return
                    void openDetailDrawer(row)
                  }}
                  aria-label={t('fileOcr.tasks.action.view')}
                />
              </Tooltip>
              <Dropdown menu={{ items: moreMenuItems }} trigger={['click']}>
                <span style={{ display: 'inline-flex' }}>
                  <Tooltip title={t('fileOcr.tasks.action.more')}>
                    <Button
                      type="text"
                      size="small"
                      icon={<MoreOutlined />}
                      aria-label={t('fileOcr.tasks.action.more')}
                    />
                  </Tooltip>
                </span>
              </Dropdown>
            </Space>
          )
        },
      },
    ],
    [
      handleDeleteOcrTask,
      handleDownloadOcrMarkdown,
      handleRetryOcrTask,
      onPendingAction,
      openDetailDrawer,
      openLogDrawer,
      statusColor,
      statusText,
      t,
    ],
  )

  /** Reset wizard states before opening create flow. */
  const openWizard = () => {
    setWizardOpen(true)
    setWizardStep(1)
    setOcrType(null)
    setUploadList([])
    setProgressMap({})
    setUploadFailedByUid({})
    setCreatedTaskCount(null)
  }

  /** Closes wizard only when no upload is running. */
  const closeWizard = () => {
    if (submitting) return
    setWizardOpen(false)
    setCreatedTaskCount(null)
  }

  /** Leave the success pane and close the modal. */
  const closeWizardAfterSuccess = () => {
    setWizardOpen(false)
    setWizardStep(1)
    setOcrType(null)
    setUploadList([])
    setProgressMap({})
    setUploadFailedByUid({})
    setCreatedTaskCount(null)
  }

  /** Modal close (X / mask / Esc): block while uploading; reset full wizard after success step. */
  const cancelWizardModal = () => {
    if (submitting) return
    if (wizardStep === 4) closeWizardAfterSuccess()
    else closeWizard()
  }

  /** Transform filter form values into API query params. */
  const toFilterParams = (values: FilterFormValues): OcrFileListParams => {
    const params: OcrFileListParams = {
      file_name: values.file_name?.trim() || undefined,
      ocr_type: values.ocr_type?.trim() || undefined,
      status: values.status?.trim() || undefined,
    }
    const range = values.create_range
    if (range != null && range.length === 2) {
      params.create_at_start = range[0].startOf('day').toISOString()
      params.create_at_end = range[1].endOf('day').toISOString()
    }
    return params
  }

  const goPickToUploadStep = () => {
    if (uploadList.length === 0) {
      void messageApi.warning(t('fileOcr.tasks.upload.empty'))
      return
    }
    setWizardStep(3)
  }

  /** Submit current filter values and reload from first page. */
  const onSearch = (values: FilterFormValues) => {
    setPage(1)
    setFilters(toFilterParams(values))
  }

  /** Clear all filters and reload first page. */
  const onReset = () => {
    filterForm.resetFields()
    setPage(1)
    setFilters({})
  }

  /** Keep upload list in local state while blocking auto-upload. */
  const uploadProps: UploadProps = {
    multiple: true,
    beforeUpload: (file) => {
      if (!validateSourceFile(file, t, messageApi)) return Upload.LIST_IGNORE
      if (uploadList.length >= MAX_FILE_COUNT) {
        void messageApi.error(t('fileOcr.tasks.upload.tooMany'))
        return Upload.LIST_IGNORE
      }
      return false
    },
    fileList: uploadList,
    onChange: ({ fileList }) => {
      setUploadList(fileList.slice(0, MAX_FILE_COUNT))
    },
  }

  /** Execute S3 uploads then create OCR task rows in one batch call. */
  const onFinishCreate = async () => {
    if (!workspaceId || ocrType == null) return
    if (uploadList.length === 0) {
      void messageApi.warning(t('fileOcr.tasks.upload.empty'))
      return
    }
    setSubmitting(true)
    setUploadFailedByUid({})
    try {
      const createBody: OcrFileCreateBody = { ocr_type: ocrType, files: [] }
      for (const item of uploadList) {
        const source = item.originFileObj
        if (source == null) continue
        if (!validateSourceFile(source, t, messageApi)) continue
        try {
          const uploaded = await uploadOcrSourceFile(workspaceId, source, (percent) => {
            setProgressMap((prev) => ({ ...prev, [item.uid]: percent }))
          })
          createBody.files.push({
            file_name: source.name,
            file_size: source.size ?? uploaded.size,
            object_key: uploaded.object_key,
          })
        } catch {
          setUploadFailedByUid((prev) => ({ ...prev, [item.uid]: true }))
        }
      }
      if (createBody.files.length === 0) {
        void messageApi.error(t('fileOcr.tasks.upload.noneSucceeded'))
        return
      }
      await createOcrFiles(workspaceId, createBody)
      setCreatedTaskCount(createBody.files.length)
      setWizardStep(4)
      setRefreshTick((n) => n + 1)
    } catch (err) {
      if (err instanceof ApiError) {
        void messageApi.error(err.message)
      } else if (err instanceof Error) {
        void messageApi.error(err.message)
      } else {
        void messageApi.error(t('common.error'))
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (!workspaceId) {
    return (
      <div className="minerva-file-ocr-tasks-page minerva-file-ocr-tasks-page--empty">
        <Empty description={t('settings.ocrNoWorkspace')} style={{ color: 'var(--minerva-ink)' }} />
      </div>
    )
  }

  return (
    <>
      <div className="minerva-file-ocr-tasks-page">
        <Card
          size="small"
          variant="borderless"
          className="minerva-file-ocr-tasks__card minerva-page-shell-card"
          style={{ minHeight: 0 }}
        >
          <Form form={filterForm} layout="inline" onFinish={onSearch} className="minerva-file-ocr-tasks__filter">
          <Form.Item name="file_name" label={t('fileOcr.tasks.filter.fileName')}>
            <Input allowClear placeholder={t('fileOcr.tasks.filter.fileNamePh')} />
          </Form.Item>
          <Form.Item name="ocr_type" label={t('fileOcr.tasks.filter.ocrType')}>
            <Select
              allowClear
              loading={ocrTypeDictQ.isLoading}
              style={{ minWidth: 140 }}
              options={ocrTypeFilterOptions}
            />
          </Form.Item>
          <Form.Item name="status" label={t('fileOcr.tasks.filter.status')}>
            <Select
              allowClear
              style={{ minWidth: 120 }}
              options={[
                { value: 'INIT', label: t('fileOcr.tasks.status.INIT') },
                { value: 'PROCESS', label: t('fileOcr.tasks.status.PROCESS') },
                { value: 'SUCCESS', label: t('fileOcr.tasks.status.SUCCESS') },
                { value: 'FAILED', label: t('fileOcr.tasks.status.FAILED') },
              ]}
            />
          </Form.Item>
          <Form.Item name="create_range" label={t('fileOcr.tasks.filter.createRange')}>
            <DatePicker.RangePicker allowClear />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button htmlType="submit" type="primary">
                {t('rules.search')}
              </Button>
              <Button onClick={onReset}>{t('rules.resetFilter')}</Button>
              <Button icon={<FileAddOutlined />} type="dashed" onClick={openWizard}>
                {t('fileOcr.tasks.add')}
              </Button>
            </Space>
          </Form.Item>
        </Form>

        {listQuery.error != null && (
          <div className="minerva-file-ocr-tasks__alert">
            <Alert
              type="error"
              showIcon
              message={listQuery.error instanceof ApiError ? listQuery.error.message : t('common.error')}
            />
          </div>
        )}

        <div ref={tableWrapRef} className="minerva-file-ocr-tasks__table-wrap">
          <Table<OcrFileListItem>
            rowKey="id"
            loading={listQuery.isFetching}
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
            className="minerva-card-table-scroll-ocr minerva-file-ocr-tasks__table"
            scroll={{ x: FILE_OCR_TASK_TABLE_SCROLL_X, y: tableBodyScrollY }}
            tableLayout="fixed"
            sticky
          />
        </div>
      </Card>
    </div>

      <Drawer
        className="minerva-file-ocr-tasks-drawer"
        title={t('fileOcr.tasks.logDrawer.title', {
          file: logTarget?.file_name?.trim() || t('fileOcr.tasks.logDrawer.unnamedFile'),
        })}
        size={720}
        open={logDrawerOpen}
        onClose={() => {
          setLogDrawerOpen(false)
          setLogTarget(null)
        }}
        destroyOnHidden
        classNames={{ body: 'minerva-scrollbar-styled' }}
        styles={{
          body: {
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            overflow: 'auto',
            paddingBottom: 8,
          },
        }}
      >
        {logQuery.error != null && (
          <Alert
            type="error"
            showIcon
            style={{ marginBottom: 12 }}
            message={logQuery.error instanceof ApiError ? logQuery.error.message : t('common.error')}
          />
        )}
        <Table<OcrFileLogItem>
          rowKey="id"
          size="small"
          loading={logQuery.isFetching}
          columns={logColumns}
          dataSource={logQuery.data?.items ?? []}
          scroll={{ x: true }}
          pagination={{
            current: logPage,
            pageSize: DEFAULT_PAGE_SIZE,
            total: logQuery.data?.total ?? 0,
            showSizeChanger: false,
            onChange: (p) => setLogPage(p),
          }}
        />
      </Drawer>

      <Drawer
        className="minerva-file-ocr-tasks-drawer"
        title={
          detailTarget?.file_name?.trim()
            ? `${detailTarget.file_name.trim()} — ${t('fileOcr.tasks.action.view')}`
            : t('fileOcr.tasks.detail.titleFallback')
        }
        size="80%"
        open={detailDrawerOpen}
        onClose={closeDetailDrawer}
        destroyOnHidden
        classNames={{ body: 'minerva-scrollbar-styled' }}
        styles={{
          body: {
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            overflow: 'auto',
            paddingBottom: 8,
          },
        }}
      >
        {detailError != null && (
          <Alert type="error" showIcon style={{ marginBottom: 12 }} message={detailError} />
        )}
        {detailLoading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
            <Spin />
          </div>
        ) : detailError != null ? null : detailLayoutData != null || detailData != null ? (
          <Tabs
            activeKey={detailTab}
            onChange={(k) => setDetailTab(k as 'layout' | 'markdown')}
            items={[
              {
                key: 'layout',
                label: t('fileOcr.tasks.detail.tabLayout', { defaultValue: '版面预览' }),
                children:
                  detailLayoutData?.pages?.length ? (
                    <LayoutPageViewer
                      pages={detailLayoutData.pages}
                      mode="source"
                      pageTitle={(n) => t('fileOcr.tasks.detail.pageTitle', { n })}
                    />
                  ) : (
                    <Alert
                      type="info"
                      showIcon
                      message={t('fileOcr.tasks.detail.layoutUnavailable', {
                        defaultValue: '暂无版面块数据（历史任务请查看 Markdown 标签）。',
                      })}
                    />
                  ),
              },
              {
                key: 'markdown',
                label: t('fileOcr.tasks.detail.tabMarkdown', { defaultValue: 'Markdown' }),
                children:
                  detailData != null && detailData.pages.length > 0 ? (
                    <div>
                      {detailData.pages.map((page, idx) => {
                        const n =
                          typeof page.page_index === 'number' ? page.page_index + 1 : idx + 1
                        return (
                          <section key={`${n}-${idx}`} style={{ marginBottom: 28 }}>
                            <h2 style={{ fontSize: 16, fontWeight: 600, margin: '0 0 12px' }}>
                              {t('fileOcr.tasks.detail.pageTitle', { n })}
                            </h2>
                            <MinervaMarkdown
                              preset="ocr"
                              markdown={page.markdown_text ?? ''}
                              images={page.images}
                              emptyFallback={
                                <span style={{ opacity: 0.65 }}>
                                  {t('fileOcr.tasks.detail.pageEmpty')}
                                </span>
                              }
                            />
                          </section>
                        )
                      })}
                    </div>
                  ) : (
                    <Empty description={t('fileOcr.tasks.detail.empty')} />
                  ),
              },
            ]}
          />
        ) : null}
      </Drawer>

      <Modal
        open={wizardOpen}
        title={t('fileOcr.tasks.wizard.title')}
        width="42vw"
        styles={{
          body: {
            display: 'flex',
            flexDirection: 'column',
            padding: 0,
            maxHeight: 'calc(100dvh - 120px)',
            minHeight: 'min(460px, 44vh)',
          },
        }}
        footer={null}
        mask={{ closable: wizardStep === 4 || !submitting }}
        keyboard={wizardStep === 4 || !submitting}
        closable={wizardStep === 4 || !submitting}
        onCancel={cancelWizardModal}
        destroyOnHidden
      >
        <div className="minerva-file-ocr-tasks__wizard-shell">
          <div className="minerva-file-ocr-tasks__wizard-scroll">
            <Steps
              current={wizardStep - 1}
              items={wizardSteps}
              className="minerva-file-ocr-tasks__wizard-steps"
              titlePlacement="vertical"
            />

            {wizardStep === 1 ? (
              <div className="minerva-file-ocr-tasks__wizard-content minerva-file-ocr-tasks__wizard-content--type">
                <div className="minerva-file-ocr-tasks__ocr-type-grid">
                  {ocrTypeOptions.map((option) => {
                    const selected = ocrType === option.value
                    return (
                      <button
                        key={option.value}
                        type="button"
                        className={`minerva-file-ocr-tasks__ocr-type-card${selected ? ' minerva-file-ocr-tasks__ocr-type-card--selected' : ''}`}
                        onClick={() => {
                          setOcrType(option.value)
                          setWizardStep(2)
                        }}
                      >
                        <div className="minerva-file-ocr-tasks__ocr-type-icon">{option.icon}</div>
                        <div className="minerva-file-ocr-tasks__ocr-type-title">{option.label}</div>
                        <div className="minerva-file-ocr-tasks__ocr-type-desc">{option.description}</div>
                      </button>
                    )
                  })}
                </div>
              </div>
            ) : wizardStep === 2 ? (
              <div className="minerva-file-ocr-tasks__wizard-content">
                <Upload.Dragger {...uploadProps} className="minerva-file-ocr-tasks__dragger">
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined />
                  </p>
                  <p className="ant-upload-text">{t('fileOcr.tasks.upload.dragTitle')}</p>
                  <ul className="minerva-file-ocr-tasks__upload-rules">
                    <li>{t('fileOcr.tasks.upload.ruleFormats')}</li>
                    <li>{t('fileOcr.tasks.upload.ruleSingleSize')}</li>
                    <li>{t('fileOcr.tasks.upload.ruleMaxCount')}</li>
                  </ul>
                  <p className="ant-upload-hint">{t('fileOcr.tasks.upload.dragHint')}</p>
                </Upload.Dragger>
              </div>
            ) : wizardStep === 3 ? (
              <div className="minerva-file-ocr-tasks__wizard-content">
                <ul className="minerva-file-ocr-tasks__wizard-upload-summary">
                  {uploadList.map((item) => (
                    <li key={item.uid}>{item.name}</li>
                  ))}
                </ul>
                {(submitting ||
                  uploadList.some(
                    (item) =>
                      uploadFailedByUid[item.uid] || (progressMap[item.uid] ?? 0) > 0,
                  )) && (
                  <div className="minerva-file-ocr-tasks__progress-list">
                    {uploadList.map((item) => (
                      <div key={item.uid} className="minerva-file-ocr-tasks__progress-item">
                        <div className="minerva-file-ocr-tasks__progress-name">{item.name}</div>
                        <Progress
                          percent={progressMap[item.uid] ?? 0}
                          status={uploadFailedByUid[item.uid] ? 'exception' : undefined}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="minerva-file-ocr-tasks__wizard-content minerva-file-ocr-tasks__wizard-content--success">
                <Result
                  status="success"
                  title={t('fileOcr.tasks.wizard.successTitle')}
                  subTitle={
                    createdTaskCount != null
                      ? t('fileOcr.tasks.createSuccess', { count: createdTaskCount })
                      : ''
                  }
                />
              </div>
            )}
          </div>

          {(wizardStep === 2 || wizardStep === 3 || wizardStep === 4) && (
            <div className="minerva-file-ocr-tasks__wizard-bar">
              {wizardStep === 2 && (
                <>
                  <Button icon={<LeftOutlined />} disabled={submitting} onClick={() => setWizardStep(1)}>
                    {t('fileOcr.tasks.wizard.prev')}
                  </Button>
                  <Button type="primary" onClick={goPickToUploadStep}>
                    {t('fileOcr.tasks.wizard.next')}
                  </Button>
                </>
              )}
              {wizardStep === 3 && (
                <>
                  <Button
                    icon={<LeftOutlined />}
                    disabled={submitting}
                    onClick={() => setWizardStep(2)}
                  >
                    {t('fileOcr.tasks.wizard.prev')}
                  </Button>
                  <Button
                    type="primary"
                    icon={<CloudUploadOutlined />}
                    loading={submitting}
                    onClick={() => void onFinishCreate()}
                  >
                    {t('fileOcr.tasks.wizard.uploadAction')}
                  </Button>
                </>
              )}
              {wizardStep === 4 && (
                <Button type="primary" onClick={closeWizardAfterSuccess}>
                  {t('fileOcr.tasks.wizard.finish')}
                </Button>
              )}
            </div>
          )}
        </div>
      </Modal>
    </>
  )
}
