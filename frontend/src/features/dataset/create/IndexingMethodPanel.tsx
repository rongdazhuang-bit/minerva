/** Dify-style indexing technique cards for the create wizard step 2. */

import { ContainerOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { Alert, Form, Input, Select, Tag, Typography } from 'antd'
import type { FormInstance } from 'antd'
import { useTranslation } from 'react-i18next'
import './IndexingMethodPanel.css'

export type IndexingFormValues = {
  indexing_technique?: 'high_quality' | 'economy'
  embedding_model_key?: string
}

export type IndexingMethodPanelProps = {
  form: FormInstance<IndexingFormValues>
  embeddingOptions: Array<{ value: string; label: string }>
  modelsLoading?: boolean
  /** Parent-child segmentation requires high-quality indexing (Dify parity). */
  economyDisabled?: boolean
  /** When true, indexing technique cards cannot be switched (settings page). */
  indexingLocked?: boolean
  /** Disable embedding model selector (settings page after indexed docs). */
  embeddingReadOnly?: boolean
  /** Hide parent-child / economy lock hint (settings page). */
  hideEconomyDisabledHint?: boolean
}

/** Indexing method selector with high-quality and economy cards. */
export function IndexingMethodPanel({
  form,
  embeddingOptions,
  modelsLoading,
  economyDisabled,
  indexingLocked,
  embeddingReadOnly,
  hideEconomyDisabledHint,
}: IndexingMethodPanelProps) {
  const { t } = useTranslation()
  const indexingTechnique = Form.useWatch('indexing_technique', form)
  const isHighQuality = indexingTechnique !== 'economy'
  const isEconomyActive = indexingTechnique === 'economy'

  const selectHighQuality = () => {
    if (indexingLocked && !isHighQuality) return
    form.setFieldValue('indexing_technique', 'high_quality')
  }

  const selectEconomy = () => {
    if (indexingLocked && isHighQuality) return
    if (economyDisabled) return
    form.setFieldsValue({
      indexing_technique: 'economy',
      embedding_model_key: undefined,
    })
  }

  const highQualityCardDisabled = Boolean(indexingLocked && !isHighQuality)
  const economyCardDisabled = Boolean(economyDisabled || (indexingLocked && isHighQuality))

  return (
    <div className="minerva-indexing-settings">
      <Typography.Title level={5} style={{ marginTop: 0, marginBottom: 4 }}>
        {t('dataset.create.field.indexing')}
      </Typography.Title>

      <Form.Item name="indexing_technique" hidden>
        <Input />
      </Form.Item>

      <div className="minerva-indexing-mode-grid">
        <div
          className={`minerva-indexing-mode-card${isHighQuality ? ' is-active' : ''}${highQualityCardDisabled ? ' is-disabled' : ''}`}
          onClick={selectHighQuality}
          role="button"
          tabIndex={highQualityCardDisabled ? -1 : 0}
          aria-disabled={highQualityCardDisabled}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') selectHighQuality()
          }}
        >
          <div className="minerva-indexing-mode-card__header">
            <div className="minerva-indexing-mode-card__icon minerva-indexing-mode-card__icon--high-quality">
              <ThunderboltOutlined />
            </div>
            <div>
              <div className="minerva-indexing-mode-card__title-row">
                <Typography.Text strong>{t('dataset.indexing.highQuality')}</Typography.Text>
                <Tag color="processing">{t('dataset.create.indexing.recommended')}</Tag>
              </div>
              <Typography.Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 4 }}>
                {t('dataset.create.indexing.highQualityDesc')}
              </Typography.Paragraph>
            </div>
          </div>
        </div>

        <div
          className={`minerva-indexing-mode-card${isEconomyActive ? ' is-active' : ''}${economyCardDisabled ? ' is-disabled' : ''}`}
          onClick={selectEconomy}
          role="button"
          tabIndex={economyCardDisabled ? -1 : 0}
          aria-disabled={economyCardDisabled}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') selectEconomy()
          }}
        >
          <div className="minerva-indexing-mode-card__header">
            <div className="minerva-indexing-mode-card__icon minerva-indexing-mode-card__icon--economy">
              <ContainerOutlined />
            </div>
            <div>
              <Typography.Text strong>{t('dataset.indexing.economy')}</Typography.Text>
              <Typography.Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 4 }}>
                {t('dataset.create.indexing.economyDesc')}
              </Typography.Paragraph>
            </div>
          </div>
        </div>
      </div>

      {isHighQuality ? (
        <Alert type="warning" showIcon message={t('dataset.create.indexing.highQualityWarning')} />
      ) : null}

      {economyDisabled && isHighQuality && !hideEconomyDisabledHint ? (
        <Typography.Text type="secondary">{t('dataset.create.segmentation.hierarchicalHighQualityOnly')}</Typography.Text>
      ) : null}

      {isHighQuality ? (
        <Form.Item
          name="embedding_model_key"
          label={t('dataset.create.field.embedding')}
          rules={[{ required: true, message: t('dataset.create.field.embeddingRequired') }]}
          style={{ marginBottom: 0 }}
        >
          <Select
            allowClear
            disabled={embeddingReadOnly}
            options={embeddingOptions}
            loading={modelsLoading}
          />
        </Form.Item>
      ) : null}
    </div>
  )
}
