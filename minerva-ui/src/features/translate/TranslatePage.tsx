/**
 * 文档翻译主页面：左侧翻译历史，右侧上传或左右段落对照。
 */
import { DeleteOutlined, DownloadOutlined, InboxOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Flex,
  Form,
  Popconfirm,
  Progress,
  Select,
  Skeleton,
  Spin,
  Tag,
  Typography,
  Upload,
} from 'antd'
import type { UploadProps } from 'antd/es/upload/interface'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import {
  createTranslateJob,
  deleteTranslateJob,
  getTranslateJob,
  listTranslateJobSegments,
  listTranslateJobs,
  translateJobDownloadUrl,
  type DocTranslateJobListItem,
} from '@/api/translate'
import { listModelProviders, type ModelProviderListItem } from '@/api/modelProviders'
import { useAuth } from '@/app/AuthContext'
import { useAppMessage } from '@/app/useAppMessage'
import {
  formatTranslateJobDate,
  isTranslateJobTerminal,
  translateJobListLabel,
} from '@/features/translate/translateJobUi'
import './TranslatePage.css'

const { Text, Title } = Typography

const ACCEPT = '.doc,.docx,.pdf,.txt,.md,.csv,.xls,.xlsx'
const LANG_OPTIONS = [
  { value: 'zh-CN', labelKey: 'translate.lang.zhCN' },
  { value: 'en', labelKey: 'translate.lang.en' },
  { value: 'ja', labelKey: 'translate.lang.ja' },
  { value: 'ko', labelKey: 'translate.lang.ko' },
] as const

const TERMINAL = new Set(['SUCCESS', 'FAILED'])

/** 工作区文档翻译页（类智能对话双栏布局）。 */
export function TranslatePage() {
  const { t } = useTranslation()
  const message = useAppMessage()
  const queryClient = useQueryClient()
  const { workspaceId } = useAuth()
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [sourceLang, setSourceLang] = useState<string>('en')
  const [targetLang, setTargetLang] = useState<string>('zh-CN')
  const [modelId, setModelId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const modelsQuery = useQuery({
    queryKey: ['translate-models', workspaceId],
    queryFn: () => listModelProviders(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const translateModels = useMemo(() => {
    const rows = modelsQuery.data ?? []
    return rows.filter(
      (m: ModelProviderListItem) =>
        m.model_type === 'translate' &&
        m.enabled &&
        Boolean(m.endpoint_url?.trim()) &&
        m.has_api_key,
    )
  }, [modelsQuery.data])

  const jobsQuery = useInfiniteQuery({
    queryKey: ['translate-jobs', workspaceId],
    queryFn: ({ pageParam }) =>
      listTranslateJobs(workspaceId!, {
        limit: 20,
        cursor: pageParam as string | undefined,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: Boolean(workspaceId),
  })

  const jobList = useMemo(
    () => jobsQuery.data?.pages.flatMap((p) => p.jobs) ?? [],
    [jobsQuery.data],
  )

  const jobQuery = useQuery({
    queryKey: ['translate-job', workspaceId, selectedJobId],
    queryFn: () => getTranslateJob(workspaceId!, selectedJobId!),
    enabled: Boolean(workspaceId && selectedJobId),
    refetchInterval: (q) => {
      const st = q.state.data?.status
      if (!st || TERMINAL.has(st)) return false
      return 3000
    },
  })

  const segmentsQuery = useQuery({
    queryKey: ['translate-segments', workspaceId, selectedJobId],
    queryFn: () => listTranslateJobSegments(workspaceId!, selectedJobId!),
    enabled: Boolean(workspaceId && selectedJobId),
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

  const modelOptions = useMemo(
    () =>
      translateModels.map((m) => ({
        value: m.id,
        label: `${m.provider_name} / ${m.model_name}`,
      })),
    [translateModels],
  )

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
      setSelectedJobId(out.id)
      setUploadFile(null)
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

  const handleShowUpload = useCallback(() => {
    setSelectedJobId(null)
  }, [])

  const handleDeleteJob = useCallback(
    async (jobId: string) => {
      if (!workspaceId) return
      try {
        await deleteTranslateJob(workspaceId, jobId)
        if (selectedJobId === jobId) setSelectedJobId(null)
        void queryClient.invalidateQueries({ queryKey: ['translate-jobs', workspaceId] })
        message.success(t('translate.deleteSuccess'))
      } catch {
        message.error(t('translate.deleteFailed'))
      }
    },
    [workspaceId, selectedJobId, queryClient, message, t],
  )

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

  const job = jobQuery.data
  const segments = segmentsQuery.data?.segments ?? []
  const showCompare = Boolean(selectedJobId && job)

  return (
    <div className="translate-page">
      <aside className="translate-page__sider">
        <Button type="primary" block onClick={handleShowUpload}>
          {t('translate.newTranslate')}
        </Button>
        <Text type="secondary" className="translate-page__sider-history-title">
          {t('translate.history')}
        </Text>
        <div className="translate-page__sider-history minerva-scrollbar-styled">
          {jobsQuery.isLoading ? (
            <Flex justify="center" style={{ padding: 12 }}>
              <Spin size="small" />
            </Flex>
          ) : jobList.length === 0 ? (
            <Text type="secondary">{t('translate.noHistory')}</Text>
          ) : (
            <div className="translate-page__sider-history-list">
              {jobList.map((j: DocTranslateJobListItem) => {
                const active = selectedJobId === j.id
                return (
                  <div
                    key={j.id}
                    className={
                      active
                        ? 'translate-page__job-row translate-page__job-row--active'
                        : 'translate-page__job-row'
                    }
                  >
                    <button
                      type="button"
                      className="translate-page__job-item"
                      onClick={() => setSelectedJobId(j.id)}
                    >
                      <span>{translateJobListLabel(j, t('translate.defaultTitle'))}</span>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {formatTranslateJobDate(j.update_at ?? j.create_at)}
                      </Text>
                    </button>
                    <Popconfirm
                      title={t('translate.deleteConfirm')}
                      onConfirm={() => void handleDeleteJob(j.id)}
                    >
                      <Button
                        type="text"
                        size="small"
                        icon={<DeleteOutlined />}
                        aria-label={t('translate.deleteJob')}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>
                  </div>
                )
              })}
            </div>
          )}
          {jobsQuery.hasNextPage ? (
            <Button
              type="link"
              size="small"
              loading={jobsQuery.isFetchingNextPage}
              onClick={() => void jobsQuery.fetchNextPage()}
            >
              {t('translate.loadMore')}
            </Button>
          ) : null}
        </div>
      </aside>

      <div className="translate-page__main">
        <div
          className={`translate-page__scroll minerva-scrollbar-thin${!showCompare && workspaceId ? ' translate-page__scroll--upload' : ''}`}
        >
          {!workspaceId ? (
            <Alert type="warning" message={t('translate.noWorkspace')} showIcon />
          ) : !showCompare ? (
            <div className="translate-page__upload-center">
              <Card className="translate-page__upload-card" title={t('translate.uploadTitle')}>
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
              </Card>
            </div>
          ) : (
            <>
              <div className="translate-page__toolbar">
                <Title level={5} style={{ margin: 0 }}>
                  {translateJobListLabel(job!, t('translate.defaultTitle'))}
                </Title>
                <Tag>{t(`translate.status.${job!.status}`, { defaultValue: job!.status })}</Tag>
                {!isTranslateJobTerminal(job!.status) ? (
                  <Progress
                    percent={job!.progress}
                    size="small"
                    style={{ width: 160, margin: 0 }}
                  />
                ) : null}
                <Text type="secondary">
                  {job!.segment_done}/{job!.segment_total}
                </Text>
                {job!.status === 'SUCCESS' ? (
                  <Button
                    icon={<DownloadOutlined />}
                    href={translateJobDownloadUrl(workspaceId!, job!.id)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {t('translate.download')}
                  </Button>
                ) : null}
              </div>
              {job!.status === 'FAILED' && job!.error_message ? (
                <Alert
                  type="error"
                  showIcon
                  message={job!.error_message}
                  style={{ marginBottom: 16 }}
                />
              ) : null}
              <div className="translate-page__compare-grid">
                <div>
                  <div className="translate-page__compare-col-title">
                    {t('translate.colSource')}
                  </div>
                  {segmentsQuery.isLoading ? (
                    <Skeleton active paragraph={{ rows: 4 }} />
                  ) : (
                    segments.map((s) => (
                      <div key={s.id} className="translate-page__segment-row">
                        {s.source_text}
                      </div>
                    ))
                  )}
                </div>
                <div>
                  <div className="translate-page__compare-col-title">
                    {t('translate.colTarget')}
                  </div>
                  {segmentsQuery.isLoading ? (
                    <Skeleton active paragraph={{ rows: 4 }} />
                  ) : (
                    segments.map((s) => (
                      <div key={s.id} className="translate-page__segment-row">
                        {s.translated_text?.trim() ? (
                          s.translated_text
                        ) : s.status === 'FAILED' ? (
                          <Text type="danger">{t('translate.segmentFailed')}</Text>
                        ) : (
                          <Text type="secondary">{t('translate.segmentPending')}</Text>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
