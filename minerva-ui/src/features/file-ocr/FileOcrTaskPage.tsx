import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  FileAddOutlined,
  InboxOutlined,
  LeftOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  RedoOutlined,
  StopOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Form,
  Input,
  Modal,
  Progress,
  Result,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Steps,
  Table,
  Tag,
  Upload,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { UploadFile, UploadProps } from 'antd/es/upload/interface'
import { useQuery } from '@tanstack/react-query'
import type { Dayjs } from 'dayjs'
import type { ReactNode } from 'react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/api/client'
import {
  createOcrFiles,
  getOcrFileOverviewStats,
  listOcrFiles,
  uploadOcrSourceFile,
  type OcrFileCreateBody,
  type OcrFileListItem,
  type OcrFileListParams,
} from '@/api/ocrTask'
import { useAuth } from '@/app/AuthContext'
import { DictText } from '@/components/dict'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import { useCountUp } from '@/hooks/useCountUp'
import { useDictItemTree } from '@/hooks/useDictItemTree'
import mineruLogo from './assets/mineru-logo.png'
import paddleOcrLogo from './assets/paddleocr-logo.jpg'
import './FileOcrTaskPage.css'

const MAX_FILE_SIZE = 50 * 1024 * 1024
const MAX_FILE_COUNT = 50
const ALLOWED_EXTS = new Set(['pdf', 'jpg', 'jpeg', 'png'])
const OCR_TYPE_DICT_CODE = 'TOOL_OCR'

type OcrTypeValue = 'PADDLE_OCR' | 'MINER_U'
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
function validateSourceFile(file: File, t: (key: string) => string) {
  const ext = fileExt(file.name)
  if (!ALLOWED_EXTS.has(ext)) {
    void message.error(t('fileOcr.tasks.upload.invalidExt'))
    return false
  }
  if (file.size > MAX_FILE_SIZE) {
    void message.error(t('fileOcr.tasks.upload.tooLarge'))
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
      value: 'MINER_U',
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
  const statsQuery = useQuery({
    queryKey: ['ocrFileOverviewStats', workspaceId],
    queryFn: () => getOcrFileOverviewStats(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const pending = statsQuery.isPending
  const err = statsQuery.error
  const stats = statsQuery.data

  const hasStats = Boolean(stats)
  const displayInit = useCountUp(stats?.init_count ?? 0, { enabled: hasStats })
  const displayProcess = useCountUp(stats?.process_count ?? 0, { enabled: hasStats })
  const displaySuccess = useCountUp(stats?.success_count ?? 0, { enabled: hasStats })
  const displayFailed = useCountUp(stats?.failed_count ?? 0, { enabled: hasStats })

  return (
    <div className="minerva-file-ocr-overview">
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
        )}
      </Spin>
    </div>
  )
}

/** Lists OCR tasks and hosts the modal wizard used to enqueue new OCR uploads. */
export function RulesFileOcrTaskPage() {
  const { t } = useTranslation()
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
      { value: 'MINER_U', label: 'MinerU' },
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

  /** Convert status code into localized text. */
  const statusText = (status: string) => {
    if (status === 'INIT') return t('fileOcr.tasks.status.INIT')
    if (status === 'PROCESS') return t('fileOcr.tasks.status.PROCESS')
    if (status === 'SUCCESS') return t('fileOcr.tasks.status.SUCCESS')
    if (status === 'FAILED') return t('fileOcr.tasks.status.FAILED')
    return status
  }

  /** Convert status code into tag color token. */
  const statusColor = (status: string) => {
    if (status === 'SUCCESS') return 'success'
    if (status === 'FAILED') return 'error'
    if (status === 'PROCESS') return 'processing'
    return 'default'
  }

  /** Build one disabled placeholder action callback. */
  const onPendingAction = (nameKey: string) => {
    void message.info(t('fileOcr.tasks.actionPending', { action: t(nameKey) }))
  }

  const columns: ColumnsType<OcrFileListItem> = useMemo(
    () => [
      {
        title: t('fileOcr.tasks.col.fileName'),
        dataIndex: 'file_name',
        key: 'file_name',
        width: 220,
        ellipsis: true,
        render: (v: string | null) => v?.trim() || '—',
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
        width: 140,
        render: (v: number | null) => formatFileSize(v),
      },
      {
        title: t('fileOcr.tasks.col.objectKey'),
        dataIndex: 'object_key',
        key: 'object_key',
        width: 280,
        ellipsis: true,
      },
      {
        title: t('fileOcr.tasks.col.pageCount'),
        dataIndex: 'page_count',
        key: 'page_count',
        width: 100,
        render: (v: number | null) => (v == null ? '—' : v),
      },
      {
        title: t('fileOcr.tasks.col.status'),
        dataIndex: 'status',
        key: 'status',
        width: 120,
        render: (v: string) => <Tag color={statusColor(v)}>{statusText(v)}</Tag>,
      },
      {
        title: t('fileOcr.tasks.col.createAt'),
        dataIndex: 'create_at',
        key: 'create_at',
        width: 180,
        render: (v: string | null) => formatDateTime(v),
      },
      {
        title: t('fileOcr.tasks.col.updateAt'),
        dataIndex: 'update_at',
        key: 'update_at',
        width: 180,
        render: (v: string | null) => formatDateTime(v),
      },
      {
        title: t('fileOcr.tasks.col.actions'),
        key: 'actions',
        width: 230,
        fixed: 'right',
        render: (_, row) => (
          <Space size={4}>
            <Button
              type="text"
              icon={<EyeOutlined />}
              onClick={() => onPendingAction('fileOcr.tasks.action.view')}
              aria-label={t('fileOcr.tasks.action.view')}
            />
            <Button
              type="text"
              icon={<RedoOutlined />}
              onClick={() => onPendingAction('fileOcr.tasks.action.retry')}
              aria-label={t('fileOcr.tasks.action.retry')}
            />
            <Button
              type="text"
              icon={<DownloadOutlined />}
              disabled={row.status !== 'SUCCESS'}
              onClick={() => onPendingAction('fileOcr.tasks.action.download')}
              aria-label={t('fileOcr.tasks.action.download')}
            />
            <Button
              type="text"
              danger
              icon={<DeleteOutlined />}
              onClick={() => onPendingAction('fileOcr.tasks.action.delete')}
              aria-label={t('fileOcr.tasks.action.delete')}
            />
            <Button
              type="text"
              icon={<StopOutlined />}
              disabled={row.status !== 'PROCESS'}
              onClick={() => onPendingAction('fileOcr.tasks.action.cancel')}
              aria-label={t('fileOcr.tasks.action.cancel')}
            />
          </Space>
        ),
      },
    ],
    [t],
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
      void message.warning(t('fileOcr.tasks.upload.empty'))
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
      if (!validateSourceFile(file, t)) return Upload.LIST_IGNORE
      if (uploadList.length >= MAX_FILE_COUNT) {
        void message.error(t('fileOcr.tasks.upload.tooMany'))
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
      void message.warning(t('fileOcr.tasks.upload.empty'))
      return
    }
    setSubmitting(true)
    setUploadFailedByUid({})
    try {
      const createBody: OcrFileCreateBody = { ocr_type: ocrType, files: [] }
      for (const item of uploadList) {
        const source = item.originFileObj
        if (source == null) continue
        if (!validateSourceFile(source, t)) continue
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
        void message.error(t('fileOcr.tasks.upload.noneSucceeded'))
        return
      }
      await createOcrFiles(workspaceId, createBody)
      setCreatedTaskCount(createBody.files.length)
      setWizardStep(4)
      setRefreshTick((n) => n + 1)
    } catch (err) {
      if (err instanceof ApiError) {
        void message.error(err.message)
      } else if (err instanceof Error) {
        void message.error(err.message)
      } else {
        void message.error(t('common.error'))
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (!workspaceId) {
    return (
      <div className="minerva-file-ocr-tasks">
        <Empty description={t('settings.ocrNoWorkspace')} style={{ color: 'var(--minerva-ink)' }} />
      </div>
    )
  }

  return (
    <div className="minerva-file-ocr-tasks">
      <Card size="small" variant="borderless" className="minerva-file-ocr-tasks__card">
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
          <Alert
            type="error"
            showIcon
            style={{ marginBottom: 12 }}
            message={listQuery.error instanceof ApiError ? listQuery.error.message : t('common.error')}
          />
        )}

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
          scroll={{ x: true, y: 'calc(100dvh - 420px)' }}
          sticky
        />
      </Card>

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
        maskClosable={wizardStep === 4 || !submitting}
        keyboard={wizardStep === 4 || !submitting}
        closable={wizardStep === 4 || !submitting}
        onCancel={cancelWizardModal}
        destroyOnClose
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
    </div>
  )
}
