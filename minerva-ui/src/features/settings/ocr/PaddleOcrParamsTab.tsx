import { Col, Form, Input, InputNumber, Row, Select, Tabs, Typography } from 'antd'
import type { TFunction } from 'i18next'
import { Fragment } from 'react'
import type { ReactNode } from 'react'

import {
  MINERU_EXTRA_FORMAT_OPTIONS,
  MINERU_MODEL_VERSION_OPTIONS,
  MINERU_OCR_TYPE_CODE,
} from './mineruParams'
import { PADDLE_OCR_TYPE_CODE } from './paddleOcrParams'

type PaddleFieldsProps = {
  /** i18n translator for settings labels. */
  t: TFunction
}

type ReadonlyParamItem = {
  /** Stable key used by React and to look up the serialized config value. */
  key: string
  /** Translated field label shown in the read-only parameter grid. */
  label: ReactNode
  /** Serialized or form-normalized value to show as plain text. */
  value: unknown
  /** Optional full-width cell span for values that need extra horizontal room. */
  span?: number
}

/**
 * Converts booleans, arrays and empty values into compact read-only text.
 */
function renderReadonlyValue(value: unknown, t: TFunction) {
  if (value === true) return t('common.yes')
  if (value === false) return t('common.no')
  if (Array.isArray(value)) {
    const text = value
      .filter((v): v is string | number | boolean => ['string', 'number', 'boolean'].includes(typeof v))
      .map((v) => String(v))
      .join(', ')
    return text || '—'
  }
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : '—'
  if (typeof value === 'string') return value.trim() ? value : '—'
  if (value == null) return '—'
  return JSON.stringify(value, null, 2)
}

/**
 * Renders OCR engine parameters as a bordered detail table.
 */
function OcrParamsReadonlyDescriptions({ items, t }: { items: ReadonlyParamItem[]; t: TFunction }) {
  const rows = items.reduce<ReadonlyParamItem[][]>((acc, item, index) => {
    if (index % 2 === 0) acc.push([item])
    else acc[acc.length - 1].push(item)
    return acc
  }, [])

  return (
    <table className="minerva-ocr-settings__params-table">
      <tbody>
        {rows.map((row) => (
          <tr key={row.map((item) => item.key).join('__')}>
            {row.map((item) => {
              const rendered = renderReadonlyValue(item.value, t)
              const isLong = typeof rendered === 'string' && (rendered.includes('\n') || rendered.length > 80)
              return (
                <Fragment key={item.key}>
                  <th scope="row">
                    {item.label}
                  </th>
                  <td>
                    {isLong ? (
                      <pre
                        className="minerva-ocr-settings__json-view"
                        style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                      >
                        {rendered}
                      </pre>
                    ) : (
                      <Typography.Text style={{ wordBreak: 'break-word' }}>{rendered}</Typography.Text>
                    )}
                  </td>
                </Fragment>
              )
            })}
            {row.length === 1 ? (
              <>
                <th aria-hidden="true" />
                <td aria-hidden="true" />
              </>
            ) : null}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/**
 * Yes / no / unset dropdown consistent with other Paddle boolean params.
 */
function triBoolSelect(t: PaddleFieldsProps['t']) {
  return (
    <Select
      allowClear
      options={[
        { value: true, label: t('common.yes') },
        { value: false, label: t('common.no') },
      ]}
    />
  )
}

/**
 * Renders PaddleOCR-VL-compatible option inputs bound to form name path `paddle`.
 */
export function PaddleOcrParamsFields({ t }: PaddleFieldsProps) {
  return (
    <Row gutter={[16, 0]}>
        <Col xs={24} sm={12}>
          <Form.Item
            name={['paddle', 'fileType']}
            label={t('settings.ocrPaddle.fileType')}
            tooltip={t('settings.ocrPaddle.fileTypeHint')}
          >
            <Select
              allowClear
              options={[
                { value: 0, label: t('settings.ocrPaddle.fileTypePdf') },
                { value: 1, label: t('settings.ocrPaddle.fileTypeImage') },
              ]}
            />
          </Form.Item>
        </Col>
        {(
          [
            ['useDocOrientationClassify', 'settings.ocrPaddle.useDocOrientationClassify'],
            ['useDocUnwarping', 'settings.ocrPaddle.useDocUnwarping'],
            ['useLayoutDetection', 'settings.ocrPaddle.useLayoutDetection'],
            ['useChartRecognition', 'settings.ocrPaddle.useChartRecognition'],
          ] as const
        ).map(([field, labelKey]) => (
          <Col xs={24} sm={12} key={field}>
            <Form.Item name={['paddle', field]} label={t(labelKey)} tooltip={t(`${labelKey}Hint`)}>
              {triBoolSelect(t)}
            </Form.Item>
          </Col>
        ))}
        <Col xs={24} sm={12}>
          <Form.Item
            name={['paddle', 'layoutThresholdText']}
            label={t('settings.ocrPaddle.layoutThreshold')}
            tooltip={t('settings.ocrPaddle.layoutThresholdHint')}
          >
            <Input.TextArea rows={2} allowClear className="minerva-ocr-json-field" />
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item
            name={['paddle', 'layoutNms']}
            label={t('settings.ocrPaddle.layoutNms')}
            tooltip={t('settings.ocrPaddle.layoutNmsHint')}
          >
            {triBoolSelect(t)}
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item
            name={['paddle', 'layoutUnclipRatioText']}
            label={t('settings.ocrPaddle.layoutUnclipRatio')}
            tooltip={t('settings.ocrPaddle.layoutUnclipRatioHint')}
          >
            <Input.TextArea rows={2} allowClear className="minerva-ocr-json-field" />
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item
            name={['paddle', 'layoutMergeBboxesMode']}
            label={t('settings.ocrPaddle.layoutMergeBboxesMode')}
            tooltip={t('settings.ocrPaddle.layoutMergeBboxesModeHint')}
          >
            <Input allowClear maxLength={256} />
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item
            name={['paddle', 'promptLabel']}
            label={t('settings.ocrPaddle.promptLabel')}
            tooltip={t('settings.ocrPaddle.promptLabelHint')}
          >
            <Input allowClear maxLength={512} />
          </Form.Item>
        </Col>
        {(
          [
            'repetitionPenalty',
            'temperature',
            'topP',
            'minPixels',
            'maxPixels',
          ] as const
        ).map((field) => (
          <Col xs={24} sm={12} key={field}>
            <Form.Item
              name={['paddle', field]}
              label={t(`settings.ocrPaddle.${field}`)}
              tooltip={t(`settings.ocrPaddle.${field}Hint`)}
            >
              <InputNumber style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        ))}
        <Col xs={24} sm={12}>
          <Form.Item
            name={['paddle', 'showFormulaNumber']}
            label={t('settings.ocrPaddle.showFormulaNumber')}
            tooltip={t('settings.ocrPaddle.showFormulaNumberHint')}
          >
            {triBoolSelect(t)}
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item
            name={['paddle', 'prettifyMarkdown']}
            label={t('settings.ocrPaddle.prettifyMarkdown')}
            tooltip={t('settings.ocrPaddle.prettifyMarkdownHint')}
          >
            {triBoolSelect(t)}
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item name={['paddle', 'visualize']} label={t('settings.ocrPaddle.visualize')} tooltip={t('settings.ocrPaddle.visualizeHint')}>
            {triBoolSelect(t)}
          </Form.Item>
        </Col>
    </Row>
  )
}

type MineruFieldsProps = {
  /** i18n translator for settings labels. */
  t: TFunction
}

/**
 * MinerU 接口扩展参数表单（布局与 Paddle 一致：`Row`/`Col`、`triBoolSelect`、`allowClear`）。
 */
export function MineruOcrParamsFields({ t }: MineruFieldsProps) {
  return (
    <Row gutter={[16, 0]}>
      <Col xs={24} sm={12}>
        <Form.Item name={['mineru', 'isOcr']} label={t('settings.ocrMineru.isOcr')} tooltip={t('settings.ocrMineru.isOcrHint')}>
          {triBoolSelect(t)}
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'enableFormula']}
          label={t('settings.ocrMineru.enableFormula')}
          tooltip={t('settings.ocrMineru.enableFormulaHint')}
        >
          {triBoolSelect(t)}
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'enableTable']}
          label={t('settings.ocrMineru.enableTable')}
          tooltip={t('settings.ocrMineru.enableTableHint')}
        >
          {triBoolSelect(t)}
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name={['mineru', 'language']} label={t('settings.ocrMineru.language')} tooltip={t('settings.ocrMineru.languageHint')}>
          <Input allowClear maxLength={32} placeholder="ch" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'dataId']}
          label={t('settings.ocrMineru.dataId')}
          tooltip={t('settings.ocrMineru.dataIdHint')}
          rules={[
            {
              pattern: /^[A-Za-z0-9._-]*$/,
              message: t('settings.ocrMineru.dataIdPattern'),
            },
          ]}
        >
          <Input allowClear maxLength={128} />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name={['mineru', 'callback']} label={t('settings.ocrMineru.callback')} tooltip={t('settings.ocrMineru.callbackHint')}>
          <Input allowClear maxLength={2048} />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'seed']}
          label={t('settings.ocrMineru.seed')}
          tooltip={t('settings.ocrMineru.seedHint')}
          dependencies={[['mineru', 'callback']]}
          rules={[
            ({ getFieldValue }) => ({
              validator(_, value) {
                const cb = getFieldValue(['mineru', 'callback']) as string | undefined
                if (cb != null && String(cb).trim().length > 0) {
                  if (value == null || String(value).trim().length === 0) {
                    return Promise.reject(new Error(t('settings.ocrMineru.seedRequired')))
                  }
                }
                return Promise.resolve()
              },
            }),
            {
              pattern: /^[A-Za-z0-9_]*$/,
              message: t('settings.ocrMineru.seedPattern'),
            },
          ]}
        >
          <Input allowClear maxLength={64} />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name={['mineru', 'extraFormats']} label={t('settings.ocrMineru.extraFormats')} tooltip={t('settings.ocrMineru.extraFormatsHint')}>
          <Select
            allowClear
            mode="multiple"
            optionFilterProp="label"
            options={MINERU_EXTRA_FORMAT_OPTIONS.map((v) => ({ value: v, label: v }))}
          />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'pageRanges']}
          label={t('settings.ocrMineru.pageRanges')}
          tooltip={t('settings.ocrMineru.pageRangesHint')}
        >
          <Input allowClear maxLength={512} placeholder="1-200" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name={['mineru', 'modelVersion']} label={t('settings.ocrMineru.modelVersion')} tooltip={t('settings.ocrMineru.modelVersionHint')}>
          <Select
            allowClear
            optionFilterProp="label"
            showSearch
            options={MINERU_MODEL_VERSION_OPTIONS.map((v) => ({ value: v, label: v }))}
          />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name={['mineru', 'noCache']} label={t('settings.ocrMineru.noCache')} tooltip={t('settings.ocrMineru.noCacheHint')}>
          {triBoolSelect(t)}
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name={['mineru', 'cacheTolerance']} label={t('settings.ocrMineru.cacheTolerance')} tooltip={t('settings.ocrMineru.cacheToleranceHint')}>
          <InputNumber style={{ width: '100%' }} min={0} precision={0} placeholder="900" />
        </Form.Item>
      </Col>
    </Row>
  )
}

/**
 * Shows Paddle OCR parameters without editable controls in the view drawer.
 */
export function PaddleOcrParamsReadonly({
  values,
  t,
}: {
  /** Form-normalized Paddle values produced from persisted `ocr_config`. */
  values: Record<string, unknown>
  t: TFunction
}) {
  const boolFields = [
    ['useDocOrientationClassify', 'settings.ocrPaddle.useDocOrientationClassify'],
    ['useDocUnwarping', 'settings.ocrPaddle.useDocUnwarping'],
    ['useLayoutDetection', 'settings.ocrPaddle.useLayoutDetection'],
    ['useChartRecognition', 'settings.ocrPaddle.useChartRecognition'],
  ] as const
  const numberFields = [
    'repetitionPenalty',
    'temperature',
    'topP',
    'minPixels',
    'maxPixels',
  ] as const
  const items: ReadonlyParamItem[] = [
    {
      key: 'fileType',
      label: t('settings.ocrPaddle.fileType'),
      value:
        values.fileType === 0
          ? t('settings.ocrPaddle.fileTypePdf')
          : values.fileType === 1
            ? t('settings.ocrPaddle.fileTypeImage')
            : undefined,
    },
    ...boolFields.map(([key, labelKey]) => ({ key, label: t(labelKey), value: values[key] })),
    {
      key: 'layoutThresholdText',
      label: t('settings.ocrPaddle.layoutThreshold'),
      value: values.layoutThresholdText,
    },
    { key: 'layoutNms', label: t('settings.ocrPaddle.layoutNms'), value: values.layoutNms },
    {
      key: 'layoutUnclipRatioText',
      label: t('settings.ocrPaddle.layoutUnclipRatio'),
      value: values.layoutUnclipRatioText,
    },
    {
      key: 'layoutMergeBboxesMode',
      label: t('settings.ocrPaddle.layoutMergeBboxesMode'),
      value: values.layoutMergeBboxesMode,
    },
    { key: 'promptLabel', label: t('settings.ocrPaddle.promptLabel'), value: values.promptLabel },
    ...numberFields.map((key) => ({
      key,
      label: t(`settings.ocrPaddle.${key}`),
      value: values[key],
    })),
    {
      key: 'showFormulaNumber',
      label: t('settings.ocrPaddle.showFormulaNumber'),
      value: values.showFormulaNumber,
    },
    {
      key: 'prettifyMarkdown',
      label: t('settings.ocrPaddle.prettifyMarkdown'),
      value: values.prettifyMarkdown,
    },
    { key: 'visualize', label: t('settings.ocrPaddle.visualize'), value: values.visualize },
  ]
  return <OcrParamsReadonlyDescriptions items={items} t={t} />
}

/**
 * Shows MinerU OCR parameters without editable controls in the view drawer.
 */
export function MineruOcrParamsReadonly({
  values,
  t,
}: {
  /** Form-normalized MinerU values produced from persisted `ocr_config`. */
  values: Record<string, unknown>
  t: TFunction
}) {
  const items: ReadonlyParamItem[] = [
    { key: 'isOcr', label: t('settings.ocrMineru.isOcr'), value: values.isOcr },
    { key: 'enableFormula', label: t('settings.ocrMineru.enableFormula'), value: values.enableFormula },
    { key: 'enableTable', label: t('settings.ocrMineru.enableTable'), value: values.enableTable },
    { key: 'language', label: t('settings.ocrMineru.language'), value: values.language },
    { key: 'dataId', label: t('settings.ocrMineru.dataId'), value: values.dataId },
    { key: 'callback', label: t('settings.ocrMineru.callback'), value: values.callback },
    { key: 'seed', label: t('settings.ocrMineru.seed'), value: values.seed },
    { key: 'extraFormats', label: t('settings.ocrMineru.extraFormats'), value: values.extraFormats },
    { key: 'pageRanges', label: t('settings.ocrMineru.pageRanges'), value: values.pageRanges },
    { key: 'modelVersion', label: t('settings.ocrMineru.modelVersion'), value: values.modelVersion },
    { key: 'noCache', label: t('settings.ocrMineru.noCache'), value: values.noCache },
    {
      key: 'cacheTolerance',
      label: t('settings.ocrMineru.cacheTolerance'),
      value: values.cacheTolerance,
    },
  ]
  return <OcrParamsReadonlyDescriptions items={items} t={t} />
}

type ParamsTabsProps = {
  /** Current OCR engine dict code (TOOL_OCR). */
  ocrType: string | undefined
  t: TFunction
}

/**
 * Bottom “参数配置” tabs with content that depends on `ocrType`.
 */
export function OcrToolParamsTabs({ ocrType, t }: ParamsTabsProps) {
  const isPaddle = ocrType === PADDLE_OCR_TYPE_CODE
  const isMineru = ocrType === MINERU_OCR_TYPE_CODE
  return (
    <Tabs
      items={[
        {
          key: 'params',
          label: t('settings.ocrParamsTab'),
          children: isPaddle ? (
            <PaddleOcrParamsFields t={t} />
          ) : isMineru ? (
            <MineruOcrParamsFields t={t} />
          ) : (
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              {t('settings.ocrParamsEnginePlaceholder')}
            </Typography.Paragraph>
          ),
        },
      ]}
    />
  )
}
