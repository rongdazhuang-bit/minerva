/** Dify-style retrieval method cards for the create wizard step 2. */

import {
  AppstoreOutlined,
  ClusterOutlined,
  FileSearchOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons'
import { Form, Input, InputNumber, Select, Slider, Switch, Tag, Tooltip, Typography } from 'antd'
import type { FormInstance } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { RetrievalFormValues, SearchMethod } from '@/features/dataset/shared/retrievalForm'
import './RetrievalSettingsPanel.css'

export type RetrievalSettingsPanelProps = {
  form: FormInstance<RetrievalFormValues>
  rerankOptions: Array<{ value: string; label: string }>
  modelsLoading?: boolean
  /** Economy indexing disables vector-based retrieval methods. */
  vectorSearchDisabled?: boolean
  /** Hide section title and subtitle (e.g. inside a drawer). */
  hideHeader?: boolean
  /** When true, retrieval method cards and controls cannot be changed. */
  retrievalLocked?: boolean
}

type MethodCard = {
  method: SearchMethod
  icon: ReactNode
  iconClass: string
  titleKey: string
  descKey: string
  recommended?: boolean
}

const METHOD_CARDS: MethodCard[] = [
  {
    method: 'semantic_search',
    icon: <AppstoreOutlined />,
    iconClass: 'minerva-retrieval-mode-card__icon--semantic',
    titleKey: 'dataset.create.retrieval.semantic.title',
    descKey: 'dataset.create.retrieval.semantic.desc',
  },
  {
    method: 'full_text_search',
    icon: <FileSearchOutlined />,
    iconClass: 'minerva-retrieval-mode-card__icon--full-text',
    titleKey: 'dataset.create.retrieval.fullText.title',
    descKey: 'dataset.create.retrieval.fullText.desc',
  },
  {
    method: 'hybrid_search',
    icon: <ClusterOutlined />,
    iconClass: 'minerva-retrieval-mode-card__icon--hybrid',
    titleKey: 'dataset.create.retrieval.hybrid.title',
    descKey: 'dataset.create.retrieval.hybrid.desc',
    recommended: true,
  },
]

/** Retrieval settings with vector, full-text, and hybrid mode cards. */
export function RetrievalSettingsPanel({
  form,
  rerankOptions,
  modelsLoading,
  vectorSearchDisabled,
  hideHeader,
  retrievalLocked,
}: RetrievalSettingsPanelProps) {
  const { t } = useTranslation()
  const searchMethod = Form.useWatch('search_method', form) as SearchMethod | undefined
  const rerankingEnabled = Form.useWatch('reranking_enable', form)
  const thresholdEnabled = Form.useWatch('score_threshold_enabled', form)
  const topK = Form.useWatch('top_k', form) ?? 3
  const scoreThreshold = Form.useWatch('score_threshold', form) ?? 0.5

  const selectMethod = (method: SearchMethod) => {
    if (retrievalLocked) return
    if (vectorSearchDisabled && (method === 'semantic_search' || method === 'hybrid_search')) return
    form.setFieldValue('search_method', method)
    if (method === 'hybrid_search' && !form.getFieldValue('reranking_enable')) {
      form.setFieldValue('reranking_enable', true)
    }
  }

  const isMethodDisabled = (method: SearchMethod) =>
    Boolean(
      retrievalLocked ||
        (vectorSearchDisabled && (method === 'semantic_search' || method === 'hybrid_search')),
    )

  return (
    <div className="minerva-retrieval-settings">
      {!hideHeader ? (
        <>
          <Typography.Title level={5} style={{ marginTop: 0, marginBottom: 4 }}>
            {t('dataset.create.retrieval.title')}
          </Typography.Title>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
            {t('dataset.create.retrieval.subtitle')}
          </Typography.Paragraph>
        </>
      ) : null}

      <Form.Item name="search_method" hidden>
        <Input />
      </Form.Item>

      {METHOD_CARDS.map((card) => {
        const active = searchMethod === card.method
        const disabled = isMethodDisabled(card.method) || Boolean(retrievalLocked && !active)
        return (
          <div
            key={card.method}
            className={`minerva-retrieval-mode-card${active ? ' is-active' : ''}${disabled ? ' is-disabled' : ''}`}
            onClick={() => selectMethod(card.method)}
            role="button"
            tabIndex={disabled ? -1 : 0}
            aria-disabled={disabled}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') selectMethod(card.method)
            }}
          >
            <div className="minerva-retrieval-mode-card__header">
              <div className={`minerva-retrieval-mode-card__icon ${card.iconClass}`}>{card.icon}</div>
              <div>
                <div className="minerva-retrieval-mode-card__title-row">
                  <Typography.Text strong>{t(card.titleKey)}</Typography.Text>
                  {card.recommended ? (
                    <Tag color="processing">{t('dataset.create.indexing.recommended')}</Tag>
                  ) : null}
                </div>
                <Typography.Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 4 }}>
                  {t(card.descKey)}
                </Typography.Paragraph>
              </div>
            </div>

            {active ? (
              <div
                className="minerva-retrieval-mode-card__body"
                onClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => event.stopPropagation()}
              >
                <div className="minerva-retrieval-field-row">
                  <div className="minerva-retrieval-field-row__label">
                    <Typography.Text>{t('dataset.create.retrieval.rerank')}</Typography.Text>
                    <Tooltip title={t('dataset.create.retrieval.rerankHint')}>
                      <QuestionCircleOutlined style={{ color: 'var(--minerva-text-secondary)' }} />
                    </Tooltip>
                  </div>
                  <Form.Item name="reranking_enable" valuePropName="checked" style={{ marginBottom: 0 }}>
                    <Switch disabled={retrievalLocked} />
                  </Form.Item>
                </div>

                {rerankingEnabled ? (
                  <Form.Item
                    name="reranking_model_key"
                    label={t('dataset.settings.rerankModel')}
                    rules={[{ required: true, message: t('dataset.settings.rerankModelRequired') }]}
                    style={{ marginBottom: 12 }}
                  >
                    <Select
                      allowClear
                      options={rerankOptions}
                      loading={modelsLoading}
                      disabled={retrievalLocked}
                    />
                  </Form.Item>
                ) : null}

                <div className="minerva-retrieval-metrics-row">
                  <div className="minerva-retrieval-metric">
                    <div className="minerva-retrieval-metric__label">
                      <Typography.Text>{t('dataset.settings.topK')}</Typography.Text>
                      <Tooltip title={t('dataset.create.retrieval.topKHint')}>
                        <QuestionCircleOutlined style={{ color: 'var(--minerva-text-secondary)' }} />
                      </Tooltip>
                    </div>
                    <div className="minerva-retrieval-metric__control">
                      <Form.Item name="top_k" style={{ marginBottom: 0 }}>
                        <InputNumber min={1} max={20} style={{ width: 72 }} disabled={retrievalLocked} />
                      </Form.Item>
                      <Slider
                        min={1}
                        max={20}
                        value={topK}
                        disabled={retrievalLocked}
                        onChange={(value) => form.setFieldValue('top_k', value)}
                      />
                    </div>
                  </div>

                  <div className="minerva-retrieval-metric">
                    <div className="minerva-retrieval-metric__label">
                      <Form.Item name="score_threshold_enabled" valuePropName="checked" style={{ marginBottom: 0 }}>
                        <Switch size="small" disabled={retrievalLocked} />
                      </Form.Item>
                      <Typography.Text>{t('dataset.create.retrieval.scoreThreshold')}</Typography.Text>
                      <Tooltip title={t('dataset.create.retrieval.scoreThresholdHint')}>
                        <QuestionCircleOutlined style={{ color: 'var(--minerva-text-secondary)' }} />
                      </Tooltip>
                    </div>
                    <div className="minerva-retrieval-metric__control">
                      <Form.Item name="score_threshold" style={{ marginBottom: 0 }}>
                        <InputNumber
                          min={0}
                          max={1}
                          step={0.05}
                          disabled={!thresholdEnabled || retrievalLocked}
                          style={{ width: 72 }}
                        />
                      </Form.Item>
                      <Slider
                        min={0}
                        max={1}
                        step={0.05}
                        disabled={!thresholdEnabled || retrievalLocked}
                        value={scoreThreshold}
                        onChange={(value) => form.setFieldValue('score_threshold', value)}
                      />
                    </div>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}
