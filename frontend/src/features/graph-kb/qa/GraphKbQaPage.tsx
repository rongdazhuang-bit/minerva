/** In-menu Q&A: mode select differs by engine (basic vs naive). */

import { useMutation, useQuery } from '@tanstack/react-query'
import { Button, Card, Empty, Form, Input, InputNumber, Select, Spin, Typography, message } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useGraphKbId } from '@/features/graph-kb/shared/GraphKbContext'
import { useAuth } from '@/app/AuthContext'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import {
  getGraphKb,
  listGraphKbQueries,
  queryGraphKb,
  type GraphKbQueryHistoryOut,
  type GraphKbQueryOut,
} from '@/features/graph-kb/api/graphKb'
import { ENGINE_GRAPHRAG } from '@/features/graph-kb/shared/graphKbForm'
import './GraphKbQaPage.css'

/** Unified query modes; engines expose a subset via ``qaModesForEngine``. */
const ALL_QA_MODES = ['local', 'global', 'hybrid', 'naive', 'basic'] as const

type QaFormValues = {
  query: string
  mode: (typeof ALL_QA_MODES)[number]
  top_k?: number
}

/** Modes allowed for an engine: GraphRAG gets basic; LightRAG gets naive. */
export function qaModesForEngine(engine: string | undefined): readonly string[] {
  if (engine === ENGINE_GRAPHRAG) {
    return ALL_QA_MODES.filter((mode) => mode !== 'naive')
  }
  return ALL_QA_MODES.filter((mode) => mode !== 'basic')
}

/** Q&A tab at `/app/graph-kb/:graphId/qa`. */
export function GraphKbQaPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const graphId = useGraphKbId()
  const [form] = Form.useForm<QaFormValues>()
  /** Latest answer shown in the result pane (live query or history). */
  const [result, setResult] = useState<GraphKbQueryOut | null>(null)
  /** History row id currently previewed. */
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null)

  const detailQ = useQuery({
    queryKey: ['graph-kb-detail', workspaceId, graphId],
    queryFn: () => getGraphKb(workspaceId!, graphId),
    enabled: Boolean(workspaceId && graphId),
  })

  const historyQ = useQuery({
    queryKey: ['graph-kb-queries', workspaceId, graphId],
    queryFn: () => listGraphKbQueries(workspaceId!, graphId, { page: 1, page_size: DEFAULT_PAGE_SIZE }),
    enabled: Boolean(workspaceId && graphId),
  })

  const engine = detailQ.data?.engine
  const modes = useMemo(() => qaModesForEngine(engine), [engine])

  useEffect(() => {
    const current = form.getFieldValue('mode') as string | undefined
    if (current && !modes.includes(current)) {
      form.setFieldValue('mode', 'hybrid')
    }
  }, [form, modes])

  const queryM = useMutation({
    mutationFn: (values: QaFormValues) =>
      queryGraphKb(workspaceId!, graphId, {
        query: values.query.trim(),
        mode: values.mode,
        top_k: values.top_k,
      }),
    onSuccess: (data) => {
      setResult(data)
      setActiveHistoryId(null)
      void historyQ.refetch()
    },
    onError: (err: Error) => message.error(err.message),
  })

  /** Preview a persisted history row without re-querying the engine. */
  const openHistory = (row: GraphKbQueryHistoryOut) => {
    setActiveHistoryId(row.id)
    setResult({
      answer: row.answer ?? '',
      citations: Array.isArray(row.citations)
        ? (row.citations as Record<string, unknown>[])
        : row.citations && typeof row.citations === 'object'
          ? [row.citations as Record<string, unknown>]
          : [],
    })
    form.setFieldsValue({
      query: row.query,
      mode: modes.includes(row.mode) ? (row.mode as QaFormValues['mode']) : 'hybrid',
    })
  }

  if (!workspaceId) {
    return <Empty description={t('settings.ocrNoWorkspace')} style={{ color: 'var(--minerva-ink)' }} />
  }

  const notReady = Boolean(detailQ.data && detailQ.data.indexing_status !== 'completed')

  return (
    <div className="minerva-graph-kb-qa-page">
      <Card size="small" variant="borderless" className="minerva-graph-kb-qa-page__card minerva-page-shell-card">
        {detailQ.isLoading ? (
          <div className="minerva-graph-kb-qa-page__empty">
            <Spin />
          </div>
        ) : notReady ? (
          <div className="minerva-graph-kb-qa-page__empty">
            <Empty description={t('graphKb.emptyNeedIndex')} />
          </div>
        ) : (
          <div className="minerva-graph-kb-qa-page__split">
            <div className="minerva-graph-kb-qa-page__left">
              <Form
                form={form}
                layout="vertical"
                initialValues={{ mode: 'hybrid', top_k: 5 }}
                onFinish={(values) => queryM.mutate(values)}
              >
                <Form.Item
                  name="query"
                  label={t('graphKb.qa.query')}
                  rules={[{ required: true, message: t('graphKb.qa.queryRequired') }]}
                >
                  <Input.TextArea
                    allowClear
                    rows={4}
                    placeholder={t('graphKb.qa.queryPh')}
                    classNames={{ textarea: 'minerva-scrollbar-thin' }}
                  />
                </Form.Item>
                <Form.Item name="mode" label={t('graphKb.qa.mode')}>
                  <Select
                    options={modes.map((mode) => ({
                      value: mode,
                      label: t(`graphKb.qa.mode.${mode}`),
                    }))}
                  />
                </Form.Item>
                <Form.Item name="top_k" label={t('graphKb.qa.topK')}>
                  <InputNumber min={1} max={50} style={{ width: '100%' }} />
                </Form.Item>
                <Button type="primary" htmlType="submit" loading={queryM.isPending}>
                  {t('graphKb.qa.submit')}
                </Button>
              </Form>

              <Typography.Text className="minerva-graph-kb-qa-page__section">
                {t('graphKb.qa.history')}
              </Typography.Text>
              <div className="minerva-graph-kb-qa-page__history minerva-scrollbar-styled">
                {(historyQ.data?.items ?? []).length === 0 ? (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('graphKb.qa.historyEmpty')} />
                ) : (
                  (historyQ.data?.items ?? []).map((row) => (
                    <button
                      key={row.id}
                      type="button"
                      className={
                        row.id === activeHistoryId
                          ? 'minerva-graph-kb-qa-page__history-item minerva-graph-kb-qa-page__history-item--active'
                          : 'minerva-graph-kb-qa-page__history-item'
                      }
                      onClick={() => openHistory(row)}
                    >
                      <Typography.Paragraph ellipsis={{ rows: 2 }} className="minerva-graph-kb-qa-page__history-q">
                        {row.query}
                      </Typography.Paragraph>
                      <Typography.Text type="secondary">
                        {t(`graphKb.qa.mode.${row.mode}`, { defaultValue: row.mode })}
                      </Typography.Text>
                    </button>
                  ))
                )}
              </div>
            </div>

            <div className="minerva-graph-kb-qa-page__right minerva-scrollbar-styled">
              <Typography.Text className="minerva-graph-kb-qa-page__section">
                {t('graphKb.qa.answer')}
              </Typography.Text>
              {result ? (
                <>
                  <Typography.Paragraph className="minerva-graph-kb-qa-page__answer" style={{ whiteSpace: 'pre-wrap' }}>
                    {result.answer || t('graphKb.qa.emptyAnswer')}
                  </Typography.Paragraph>
                  <Typography.Text className="minerva-graph-kb-qa-page__section">
                    {t('graphKb.qa.citations')}
                  </Typography.Text>
                  {result.citations.length === 0 ? (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('graphKb.qa.noCitations')} />
                  ) : (
                    result.citations.map((item, index) => (
                      <pre key={index} className="minerva-graph-kb-qa-page__citation minerva-scrollbar-thin">
                        {JSON.stringify(item, null, 2)}
                      </pre>
                    ))
                  )}
                </>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('graphKb.qa.resultHint')} />
              )}
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
