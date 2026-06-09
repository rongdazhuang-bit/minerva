/** Dify-style segmentation mode cards for the create wizard step 2. */

import { ApartmentOutlined, QuestionCircleOutlined, SettingOutlined } from '@ant-design/icons'
import { Button, Checkbox, Form, Input, InputNumber, Radio, Select, Space, Tooltip, Typography } from 'antd'
import type { FormInstance, Rule } from 'antd'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { ChunkingFormValues, ParentModeType } from '@/features/dataset/shared/chunkingForm'
import './SegmentationSettingsPanel.css'

export type SegmentationSettingsPanelProps = {
  form: FormInstance<ChunkingFormValues>
  onPreview: () => void
  onReset: () => void
  previewLoading?: boolean
}

/** Shared preprocessing rule checkboxes for general and hierarchical modes. */
function PreprocessRulesFields() {
  const { t } = useTranslation()

  return (
    <div className="minerva-segmentation-preprocess-rules">
      <Typography.Text type="secondary">{t('dataset.create.segmentation.preprocessTitle')}</Typography.Text>
      <Form.Item name="remove_extra_spaces" valuePropName="checked" style={{ marginBottom: 8, marginTop: 8 }}>
        <Checkbox>{t('dataset.create.field.removeSpaces')}</Checkbox>
      </Form.Item>
      <Form.Item name="remove_urls_emails" valuePropName="checked" style={{ marginBottom: 8 }}>
        <Checkbox>{t('dataset.create.field.removeUrls')}</Checkbox>
      </Form.Item>
      <Form.Item name="recognize_formula" valuePropName="checked" style={{ marginBottom: 8 }}>
        <Checkbox>{t('dataset.create.field.recognizeFormula')}</Checkbox>
      </Form.Item>
      <Form.Item name="recognize_table" valuePropName="checked" style={{ marginBottom: 12 }}>
        <Checkbox>{t('dataset.create.field.recognizeTable')}</Checkbox>
      </Form.Item>
    </div>
  )
}

/** Segmentation settings with General and Parent-child mode cards. */
export function SegmentationSettingsPanel({
  form,
  onPreview,
  onReset,
  previewLoading,
}: SegmentationSettingsPanelProps) {
  const { t } = useTranslation()
  const docForm = Form.useWatch('doc_form', form)
  const parentModeType = Form.useWatch('parent_mode_type', form) as ParentModeType | undefined
  const useQa = Form.useWatch('use_qa_segmentation', form)

  const isGeneralActive = docForm === 'text_model' || docForm === 'qa_model'
  const isHierarchicalActive = docForm === 'hierarchical_model'

  const delimiterRules = useMemo<Rule[]>(
    () => [{ required: true, whitespace: true, message: t('dataset.create.field.delimiterRequired') }],
    [t],
  )
  const maxLengthRules = useMemo<Rule[]>(
    () => [{ required: true, message: t('dataset.create.field.maxLengthRequired') }],
    [t],
  )
  const overlapRules = useMemo<Rule[]>(
    () => [{ required: true, message: t('dataset.create.field.overlapRequired') }],
    [t],
  )

  const selectGeneral = () => {
    const qa = form.getFieldValue('use_qa_segmentation') === true
    form.setFieldValue('doc_form', qa ? 'qa_model' : 'text_model')
  }

  const selectHierarchical = () => {
    const current = form.getFieldsValue()
    form.setFieldsValue({
      doc_form: 'hierarchical_model',
      use_qa_segmentation: false,
      parent_mode_type: current.parent_mode_type ?? 'paragraph',
      parent_delimiter: current.parent_delimiter ?? '\\n\\n',
      parent_max_length: current.parent_max_length ?? 1024,
      sub_delimiter: current.sub_delimiter ?? '\\n',
      sub_max_length: current.sub_max_length ?? 512,
    })
  }

  const onQaToggle = (checked: boolean) => {
    form.setFieldsValue({
      use_qa_segmentation: checked,
      doc_form: checked ? 'qa_model' : 'text_model',
    })
  }

  return (
    <div className="minerva-segmentation-settings">
      <Typography.Title level={5} style={{ marginTop: 0, marginBottom: 4 }}>
        {t('dataset.create.segmentation.title')}
      </Typography.Title>

      <div
        className={`minerva-segmentation-mode-card${isGeneralActive ? ' is-active' : ''}`}
        onClick={selectGeneral}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') selectGeneral()
        }}
      >
        <div className="minerva-segmentation-mode-card__header">
          <div className="minerva-segmentation-mode-card__icon minerva-segmentation-mode-card__icon--general">
            <SettingOutlined />
          </div>
          <div>
            <Typography.Text strong>{t('dataset.create.segmentation.general.title')}</Typography.Text>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 4 }}>
              {t('dataset.create.segmentation.general.desc')}
            </Typography.Paragraph>
          </div>
        </div>

        {isGeneralActive ? (
          <div
            className="minerva-segmentation-mode-card__body"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => event.stopPropagation()}
          >
            <div className="minerva-segmentation-field-row minerva-segmentation-field-row--triple">
              <Form.Item
                name="delimiter"
                label={
                  <Space size={4}>
                    {t('dataset.create.field.delimiter')}
                    <Tooltip title={t('dataset.create.segmentation.delimiterHint')}>
                      <QuestionCircleOutlined />
                    </Tooltip>
                  </Space>
                }
                rules={delimiterRules}
              >
                <Input allowClear placeholder="\\n\\n" />
              </Form.Item>
              <Form.Item name="max_length" label={t('dataset.create.field.maxLength')} rules={maxLengthRules}>
                <InputNumber min={100} max={8192} addonAfter={t('dataset.create.segmentation.charUnit')} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item
                name="chunk_overlap"
                label={
                  <Space size={4}>
                    {t('dataset.create.field.overlap')}
                    <Tooltip title={t('dataset.create.segmentation.overlapHint')}>
                      <QuestionCircleOutlined />
                    </Tooltip>
                  </Space>
                }
                rules={overlapRules}
              >
                <InputNumber min={0} max={500} addonAfter={t('dataset.create.segmentation.charUnit')} style={{ width: '100%' }} />
              </Form.Item>
            </div>

            <PreprocessRulesFields />

            <Space align="center" wrap>
              <Form.Item name="use_qa_segmentation" valuePropName="checked" style={{ marginBottom: 0 }}>
                <Checkbox onChange={(event) => onQaToggle(event.target.checked)}>
                  <Space size={4}>
                    {t('dataset.create.segmentation.qaToggle')}
                    <Tooltip title={t('dataset.create.segmentation.qaHint')}>
                      <QuestionCircleOutlined />
                    </Tooltip>
                  </Space>
                </Checkbox>
              </Form.Item>
              <Form.Item name="qa_language" style={{ marginBottom: 0 }}>
                <Select
                  disabled={!useQa}
                  style={{ width: 160 }}
                  options={[{ value: 'Chinese Simplified', label: t('dataset.create.segmentation.qaLangZh') }]}
                />
              </Form.Item>
            </Space>

            <div className="minerva-segmentation-actions">
              <Button type="primary" loading={previewLoading} onClick={onPreview}>
                {t('dataset.create.previewChunks')}
              </Button>
              <Button type="link" onClick={onReset}>
                {t('dataset.create.segmentation.reset')}
              </Button>
            </div>
          </div>
        ) : null}
      </div>

      <div
        className={`minerva-segmentation-mode-card${isHierarchicalActive ? ' is-active' : ''}`}
        onClick={selectHierarchical}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') selectHierarchical()
        }}
      >
        <div className="minerva-segmentation-mode-card__header">
          <div className="minerva-segmentation-mode-card__icon minerva-segmentation-mode-card__icon--hierarchical">
            <ApartmentOutlined />
          </div>
          <div>
            <Typography.Text strong>{t('dataset.create.segmentation.hierarchical.title')}</Typography.Text>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 4 }}>
              {t('dataset.create.segmentation.hierarchical.desc')}
            </Typography.Paragraph>
          </div>
        </div>

        {isHierarchicalActive ? (
          <div
            className="minerva-segmentation-mode-card__body"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => event.stopPropagation()}
          >
            <div className="minerva-segmentation-subsection">
              <Typography.Text strong>{t('dataset.create.segmentation.parentContext')}</Typography.Text>
              <Form.Item name="parent_mode_type" style={{ marginTop: 8, marginBottom: 12 }}>
                <Radio.Group>
                  <Space direction="vertical" size={8}>
                    <Radio value="paragraph">
                      <Space direction="vertical" size={0}>
                        <Typography.Text>{t('dataset.create.segmentation.parentParagraph')}</Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {t('dataset.create.segmentation.parentParagraphDesc')}
                        </Typography.Text>
                      </Space>
                    </Radio>
                    <Radio value="full-doc">
                      <Space direction="vertical" size={0}>
                        <Typography.Text>{t('dataset.create.segmentation.parentFullDoc')}</Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {t('dataset.create.segmentation.parentFullDocDesc')}
                        </Typography.Text>
                      </Space>
                    </Radio>
                  </Space>
                </Radio.Group>
              </Form.Item>

              {parentModeType !== 'full-doc' ? (
                <div className="minerva-segmentation-field-row">
                  <Form.Item
                    name="parent_delimiter"
                    label={t('dataset.create.field.delimiter')}
                    rules={delimiterRules}
                  >
                    <Input allowClear placeholder="\\n\\n" />
                  </Form.Item>
                  <Form.Item
                    name="parent_max_length"
                    label={t('dataset.create.field.maxLength')}
                    rules={maxLengthRules}
                  >
                    <InputNumber
                      min={200}
                      max={8192}
                      addonAfter={t('dataset.create.segmentation.charUnit')}
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                </div>
              ) : null}
            </div>

            <div className="minerva-segmentation-subsection">
              <Typography.Text strong>{t('dataset.create.segmentation.childRetrieval')}</Typography.Text>
              <div className="minerva-segmentation-field-row" style={{ marginTop: 8 }}>
                <Form.Item name="sub_delimiter" label={t('dataset.create.field.delimiter')} rules={delimiterRules}>
                  <Input allowClear placeholder="\\n" />
                </Form.Item>
                <Form.Item name="sub_max_length" label={t('dataset.create.field.maxLength')} rules={maxLengthRules}>
                  <InputNumber
                    min={100}
                    max={4096}
                    addonAfter={t('dataset.create.segmentation.charUnit')}
                    style={{ width: '100%' }}
                  />
                </Form.Item>
              </div>
            </div>

            <PreprocessRulesFields />

            <div className="minerva-segmentation-actions">
              <Button type="primary" loading={previewLoading} onClick={onPreview}>
                {t('dataset.create.previewChunks')}
              </Button>
              <Button type="link" onClick={onReset}>
                {t('dataset.create.segmentation.reset')}
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
