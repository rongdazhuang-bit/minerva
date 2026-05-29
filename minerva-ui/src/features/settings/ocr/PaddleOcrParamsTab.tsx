import { Col, Form, Input, InputNumber, Row, Select, Tabs, Typography } from 'antd'
import type { TFunction } from 'i18next'
import { Fragment } from 'react'
import type { ReactNode } from 'react'

import {
  MINERU_BACKEND_OPTIONS,
  MINERU_LANG_OPTIONS,
  MINERU_OCR_TYPE_CODE,
  MINERU_PARSE_METHOD_OPTIONS,
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
            name={['paddle', 'mergeLayoutBlocks']}
            label={t('settings.ocrPaddle.mergeLayoutBlocks')}
            tooltip={t('settings.ocrPaddle.mergeLayoutBlocksHint')}
          >
            {triBoolSelect(t)}
          </Form.Item>
        </Col>
        {(
          [
            ['useDocOrientationClassify', 'settings.ocrPaddle.useDocOrientationClassify'],
            ['useDocUnwarping', 'settings.ocrPaddle.useDocUnwarping'],
            ['useLayoutDetection', 'settings.ocrPaddle.useLayoutDetection'],
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
            name={['paddle', 'formatBlockContent']}
            label={t('settings.ocrPaddle.formatBlockContent')}
            tooltip={t('settings.ocrPaddle.formatBlockContentHint')}
          >
            {triBoolSelect(t)}
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item
            name={['paddle', 'useChartRecognition']}
            label={t('settings.ocrPaddle.useChartRecognition')}
            tooltip={t('settings.ocrPaddle.useChartRecognitionHint')}
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
 * MinerU self-hosted API parameter form (layout aligned with Paddle).
 */
export function MineruOcrParamsFields({ t }: MineruFieldsProps) {
  return (
    <Row gutter={[16, 0]}>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'outputDir']}
          label={t('settings.ocrMineru.outputDir')}
          tooltip={t('settings.ocrMineru.outputDirHint')}
        >
          <Input allowClear maxLength={512} placeholder="./output" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'langList']}
          label={t('settings.ocrMineru.langList')}
          tooltip={t('settings.ocrMineru.langListHint')}
        >
          <Select
            allowClear
            mode="multiple"
            optionFilterProp="label"
            options={MINERU_LANG_OPTIONS.map((v) => ({ value: v, label: v }))}
          />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'backend']}
          label={t('settings.ocrMineru.backend')}
          tooltip={t('settings.ocrMineru.backendHint')}
        >
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            options={MINERU_BACKEND_OPTIONS.map((v) => ({ value: v, label: v }))}
          />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'parseMethod']}
          label={t('settings.ocrMineru.parseMethod')}
          tooltip={t('settings.ocrMineru.parseMethodHint')}
        >
          <Select
            allowClear
            optionFilterProp="label"
            options={MINERU_PARSE_METHOD_OPTIONS.map((v) => ({ value: v, label: v }))}
          />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'formulaEnable']}
          label={t('settings.ocrMineru.formulaEnable')}
          tooltip={t('settings.ocrMineru.formulaEnableHint')}
        >
          {triBoolSelect(t)}
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'tableEnable']}
          label={t('settings.ocrMineru.tableEnable')}
          tooltip={t('settings.ocrMineru.tableEnableHint')}
        >
          {triBoolSelect(t)}
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'serverUrl']}
          label={t('settings.ocrMineru.serverUrl')}
          tooltip={t('settings.ocrMineru.serverUrlHint')}
          dependencies={[['mineru', 'backend']]}
          rules={[
            ({ getFieldValue }) => ({
              validator(_, value) {
                const backend = getFieldValue(['mineru', 'backend']) as string | undefined
                if (backend != null && String(backend).includes('http-client')) {
                  if (value == null || String(value).trim().length === 0) {
                    return Promise.reject(new Error(t('settings.ocrMineru.serverUrlRequired')))
                  }
                }
                return Promise.resolve()
              },
            }),
          ]}
        >
          <Input allowClear maxLength={2048} placeholder="http://127.0.0.1:30000" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'returnMd']}
          label={t('settings.ocrMineru.returnMd')}
          tooltip={t('settings.ocrMineru.returnMdHint')}
        >
          {triBoolSelect(t)}
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'returnMiddleJson']}
          label={t('settings.ocrMineru.returnMiddleJson')}
          tooltip={t('settings.ocrMineru.returnMiddleJsonHint')}
        >
          {triBoolSelect(t)}
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'returnModelOutput']}
          label={t('settings.ocrMineru.returnModelOutput')}
          tooltip={t('settings.ocrMineru.returnModelOutputHint')}
        >
          {triBoolSelect(t)}
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'returnContentList']}
          label={t('settings.ocrMineru.returnContentList')}
          tooltip={t('settings.ocrMineru.returnContentListHint')}
        >
          {triBoolSelect(t)}
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'returnImages']}
          label={t('settings.ocrMineru.returnImages')}
          tooltip={t('settings.ocrMineru.returnImagesHint')}
        >
          {triBoolSelect(t)}
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'responseFormatZip']}
          label={t('settings.ocrMineru.responseFormatZip')}
          tooltip={t('settings.ocrMineru.responseFormatZipHint')}
        >
          {triBoolSelect(t)}
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'startPageId']}
          label={t('settings.ocrMineru.startPageId')}
          tooltip={t('settings.ocrMineru.startPageIdHint')}
        >
          <InputNumber style={{ width: '100%' }} min={0} precision={0} />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name={['mineru', 'endPageId']}
          label={t('settings.ocrMineru.endPageId')}
          tooltip={t('settings.ocrMineru.endPageIdHint')}
        >
          <InputNumber style={{ width: '100%' }} min={0} precision={0} />
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
      key: 'mergeLayoutBlocks',
      label: t('settings.ocrPaddle.mergeLayoutBlocks'),
      value: values.mergeLayoutBlocks,
    },
    ...boolFields.map(([key, labelKey]) => ({ key, label: t(labelKey), value: values[key] })),
    {
      key: 'layoutThresholdText',
      label: t('settings.ocrPaddle.layoutThreshold'),
      value: values.layoutThresholdText,
    },
    { key: 'layoutNms', label: t('settings.ocrPaddle.layoutNms'), value: values.layoutNms },
    {
      key: 'formatBlockContent',
      label: t('settings.ocrPaddle.formatBlockContent'),
      value: values.formatBlockContent,
    },
    {
      key: 'useChartRecognition',
      label: t('settings.ocrPaddle.useChartRecognition'),
      value: values.useChartRecognition,
    },
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
  const boolFields = [
    ['formulaEnable', 'settings.ocrMineru.formulaEnable'],
    ['tableEnable', 'settings.ocrMineru.tableEnable'],
    ['returnMd', 'settings.ocrMineru.returnMd'],
    ['returnMiddleJson', 'settings.ocrMineru.returnMiddleJson'],
    ['returnModelOutput', 'settings.ocrMineru.returnModelOutput'],
    ['returnContentList', 'settings.ocrMineru.returnContentList'],
    ['returnImages', 'settings.ocrMineru.returnImages'],
    ['responseFormatZip', 'settings.ocrMineru.responseFormatZip'],
  ] as const
  const items: ReadonlyParamItem[] = [
    { key: 'outputDir', label: t('settings.ocrMineru.outputDir'), value: values.outputDir },
    { key: 'langList', label: t('settings.ocrMineru.langList'), value: values.langList },
    { key: 'backend', label: t('settings.ocrMineru.backend'), value: values.backend },
    { key: 'parseMethod', label: t('settings.ocrMineru.parseMethod'), value: values.parseMethod },
    ...boolFields.map(([key, labelKey]) => ({ key, label: t(labelKey), value: values[key] })),
    { key: 'serverUrl', label: t('settings.ocrMineru.serverUrl'), value: values.serverUrl },
    {
      key: 'startPageId',
      label: t('settings.ocrMineru.startPageId'),
      value: values.startPageId,
    },
    { key: 'endPageId', label: t('settings.ocrMineru.endPageId'), value: values.endPageId },
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
