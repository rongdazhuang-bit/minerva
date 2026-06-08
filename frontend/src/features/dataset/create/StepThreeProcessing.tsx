/** Step 3 — Dify-style completion card with embedding progress polling. */

import {
  AppstoreOutlined,
  ArrowRightOutlined,
  BookOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  CodeOutlined,
  FileTextOutlined,
  LoadingOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { Button, Input, Typography, message } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { patchDataset } from '@/features/dataset/api/hitTesting'
import { getBatchIndexingStatus, type BatchIndexingStatusOut } from '@/features/dataset/api/datasets'
import {
  buildCompletionSummaryRows,
  type CreateCompletionSnapshot,
} from '@/features/dataset/create/createCompletionSummary'
import './StepThreeProcessing.css'

export type StepThreeDocument = {
  id: string
  name: string
}

export type StepThreeProcessingProps = {
  workspaceId: string
  datasetId: string
  batch: string
  datasetName: string
  onDatasetNameChange: (name: string) => void
  documents: StepThreeDocument[]
  formSnapshot?: CreateCompletionSnapshot | null
  status: BatchIndexingStatusOut | null
  onStatusChange: (status: BatchIndexingStatusOut) => void
  onFinished: () => void
  onGoToDocuments: () => void
  /** Append-documents flow uses a compact progress layout without the success card. */
  isAppend?: boolean
}

/** Poll batch indexing status and render Dify-style completion UI. */
export function StepThreeProcessing({
  workspaceId,
  datasetId,
  batch,
  datasetName,
  onDatasetNameChange,
  documents,
  formSnapshot,
  status,
  onStatusChange,
  onFinished,
  onGoToDocuments,
  isAppend = false,
}: StepThreeProcessingProps) {
  const { t } = useTranslation()
  const [nameDraft, setNameDraft] = useState(datasetName)
  const [savingName, setSavingName] = useState(false)

  useEffect(() => {
    setNameDraft(datasetName)
  }, [datasetName])

  useEffect(() => {
    let cancelled = false

    const tick = async () => {
      const next = await getBatchIndexingStatus(workspaceId, datasetId, batch)
      if (cancelled) return
      onStatusChange(next)
      if (next.completed + next.failed >= next.total) {
        onFinished()
        return
      }
      window.setTimeout(() => void tick(), 2000)
    }

    void tick()
    return () => {
      cancelled = true
    }
  }, [batch, datasetId, onFinished, onStatusChange, workspaceId])

  const statusByDocId = useMemo(() => {
    const map = new Map<string, { status: string; error?: string | null }>()
    for (const row of status?.documents ?? []) {
      map.set(row.id, { status: row.indexing_status, error: row.error })
    }
    return map
  }, [status?.documents])

  const total = status?.total ?? documents.length
  const completed = status?.completed ?? 0
  const failed = status?.failed ?? 0
  const allDone = total > 0 && completed + failed >= total
  const embeddingTitle = allDone
    ? t('dataset.create.complete.embeddingDone')
    : t('dataset.create.complete.embeddingInProgress')

  const summaryRows = useMemo(
    () => (formSnapshot ? buildCompletionSummaryRows(formSnapshot, t) : []),
    [formSnapshot, t],
  )

  const persistName = useCallback(async () => {
    const trimmed = nameDraft.trim()
    if (!trimmed || trimmed === datasetName) return
    setSavingName(true)
    try {
      await patchDataset(workspaceId, datasetId, { name: trimmed })
      onDatasetNameChange(trimmed)
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('dataset.create.complete.renameFailed'))
      setNameDraft(datasetName)
    } finally {
      setSavingName(false)
    }
  }, [datasetId, datasetName, nameDraft, onDatasetNameChange, t, workspaceId])

  const renderFileStatus = (docId: string) => {
    const row = statusByDocId.get(docId)
    if (!row) {
      return <LoadingOutlined spin className="minerva-dataset-step-three__file-status" />
    }
    if (row.status === 'completed') {
      return (
        <CheckCircleFilled className="minerva-dataset-step-three__file-status minerva-dataset-step-three__file-status--done" />
      )
    }
    if (row.status === 'error') {
      return (
        <CloseCircleFilled className="minerva-dataset-step-three__file-status minerva-dataset-step-three__file-status--error" />
      )
    }
    return <LoadingOutlined spin className="minerva-dataset-step-three__file-status" />
  }

  return (
    <div className={`minerva-dataset-step-three minerva-scrollbar-thin${isAppend ? ' minerva-dataset-step-three--append' : ''}`}>
      <div className="minerva-dataset-step-three__layout">
        <div className="minerva-dataset-step-three__main">
          {!isAppend ? (
            <>
              <Typography.Title level={4} className="minerva-dataset-step-three__celebrate">
                {t('dataset.create.complete.title')}
              </Typography.Title>
              <Typography.Text type="secondary" className="minerva-dataset-step-three__subtitle">
                {t('dataset.create.complete.subtitle')}
              </Typography.Text>

              <label className="minerva-dataset-step-three__field-label" htmlFor="dataset-create-name">
                {t('dataset.create.field.name')}
              </label>
              <Input
                id="dataset-create-name"
                allowClear
                className="minerva-dataset-step-three__name-input"
                value={nameDraft}
                disabled={savingName}
                prefix={<BookOutlined className="minerva-dataset-step-three__name-icon" />}
                onChange={(event) => setNameDraft(event.target.value)}
                onBlur={() => void persistName()}
                onPressEnter={() => void persistName()}
              />
            </>
          ) : (
            <Typography.Title level={5} style={{ marginTop: 0, marginBottom: 16 }}>
              {t('dataset.create.processingTitle')}
            </Typography.Title>
          )}

          <p className="minerva-dataset-step-three__section-title">{embeddingTitle}</p>
          <div className="minerva-dataset-step-three__file-list">
            {documents.map((doc) => (
              <div key={doc.id} className="minerva-dataset-step-three__file-row">
                <FileTextOutlined />
                <span className="minerva-dataset-step-three__file-name">{doc.name}</span>
                {renderFileStatus(doc.id)}
              </div>
            ))}
          </div>

          {!isAppend && formSnapshot ? (
            <div className="minerva-dataset-step-three__summary">
              {summaryRows.map((row) => (
                <div key={row.label} className="minerva-dataset-step-three__summary-row">
                  <span className="minerva-dataset-step-three__summary-label">{row.label}</span>
                  <span className="minerva-dataset-step-three__summary-value">
                    {row.icon === 'indexing' ? (
                      <ThunderboltOutlined className="minerva-dataset-step-three__summary-icon minerva-dataset-step-three__summary-icon--indexing" />
                    ) : null}
                    {row.icon === 'retrieval' ? (
                      <AppstoreOutlined className="minerva-dataset-step-three__summary-icon minerva-dataset-step-three__summary-icon--retrieval" />
                    ) : null}
                    {row.value}
                  </span>
                </div>
              ))}
            </div>
          ) : null}

          {!isAppend ? (
            <div className="minerva-dataset-step-three__actions">
              <Button
                icon={<CodeOutlined />}
                onClick={() => message.info(t('dataset.create.complete.apiHint'))}
              >
                {t('dataset.create.complete.accessApi')}
              </Button>
              <Button type="primary" disabled={!allDone} onClick={onGoToDocuments}>
                {t('dataset.create.complete.goToDocuments')}
                <ArrowRightOutlined />
              </Button>
            </div>
          ) : null}

          {isAppend && allDone ? (
            <div className="minerva-dataset-step-three__actions">
              <Button type="primary" onClick={onGoToDocuments}>
                {t('dataset.create.finish')}
              </Button>
            </div>
          ) : null}
        </div>

        {!isAppend ? (
          <aside className="minerva-dataset-step-three__aside">
            <div className="minerva-dataset-step-three__aside-icon">
              <BookOutlined />
            </div>
            <Typography.Title level={5} className="minerva-dataset-step-three__aside-title">
              {t('dataset.create.complete.nextTitle')}
            </Typography.Title>
            <Typography.Text type="secondary" className="minerva-dataset-step-three__aside-desc">
              {t('dataset.create.complete.nextDesc')}
            </Typography.Text>
            <Button type="link" className="minerva-dataset-step-three__aside-link">
              {t('dataset.create.complete.learnMore')}
            </Button>
          </aside>
        ) : null}
      </div>
    </div>
  )
}
