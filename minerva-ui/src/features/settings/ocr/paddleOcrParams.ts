/**
 * Serializes PaddleOCR-VL-style options for persistence in `ocr_config` (camelCase keys).
 */

/** Dictionary item code for Paddle layout (TOOL_OCR). */
export const PADDLE_OCR_TYPE_CODE = 'PADDLE_OCR'

/** Default layout score threshold when the pipeline does not override (hint: ~0.5). */
export const PADDLE_DEFAULT_LAYOUT_THRESHOLD_TEXT = '0.5'

/** Default box expansion ratio when the pipeline does not override (hint: 1.0). */
export const PADDLE_DEFAULT_LAYOUT_UNCLIP_TEXT = '1.0'

/** Default overlap merge mode when unset (hint: large). */
export const PADDLE_DEFAULT_MERGE_BBOXES_MODE = 'large'

const TRISTATE_BOOL_KEYS = [
  'useDocOrientationClassify',
  'useDocUnwarping',
  'useLayoutDetection',
  'useChartRecognition',
  'layoutNms',
  'visualize',
] as const

const OPTIONAL_NUMBER_KEYS = [
  'repetitionPenalty',
  'temperature',
  'topP',
  'minPixels',
  'maxPixels',
] as const

/** Multi-shape JSON fields still edited as text (number or object). */
const JSON_TEXT_FIELDS: { apiKey: string; textKey: string }[] = [
  { apiKey: 'layoutThreshold', textKey: 'layoutThresholdText' },
  { apiKey: 'layoutUnclipRatio', textKey: 'layoutUnclipRatioText' },
]

function stringifyJsonField(value: unknown): string {
  if (value === undefined || value === null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

/**
 * Baseline paddle form slice for new tools and missing keys (matches documented defaults).
 */
export function defaultPaddleFormValues(): Record<string, unknown> {
  return {
    layoutThresholdText: PADDLE_DEFAULT_LAYOUT_THRESHOLD_TEXT,
    layoutUnclipRatioText: PADDLE_DEFAULT_LAYOUT_UNCLIP_TEXT,
    layoutMergeBboxesMode: PADDLE_DEFAULT_MERGE_BBOXES_MODE,
    prettifyMarkdown: true,
    showFormulaNumber: false,
  }
}

/**
 * Maps stored `ocr_config` into flat form values under the `paddle` prefix.
 */
export function ocrConfigToPaddleFormValues(
  raw: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  const out: Record<string, unknown> = { ...defaultPaddleFormValues() }
  if (!raw || typeof raw !== 'object') {
    return out
  }

  if ('prettifyMarkdown' in raw) {
    out.prettifyMarkdown = raw.prettifyMarkdown !== false
  }
  if ('showFormulaNumber' in raw) {
    out.showFormulaNumber = raw.showFormulaNumber === true
  }

  if (typeof raw.fileType === 'number') out.fileType = raw.fileType
  for (const k of TRISTATE_BOOL_KEYS) {
    if (raw[k] === true || raw[k] === false) out[k] = raw[k]
  }
  if (typeof raw.promptLabel === 'string' && raw.promptLabel.length > 0) {
    out.promptLabel = raw.promptLabel
  }
  for (const k of OPTIONAL_NUMBER_KEYS) {
    if (typeof raw[k] === 'number' && !Number.isNaN(raw[k])) out[k] = raw[k]
  }

  for (const { apiKey, textKey } of JSON_TEXT_FIELDS) {
    if (raw[apiKey] !== undefined && raw[apiKey] !== null) {
      out[textKey] = stringifyJsonField(raw[apiKey])
    }
  }

  if (raw.layoutMergeBboxesMode !== undefined && raw.layoutMergeBboxesMode !== null) {
    out.layoutMergeBboxesMode = stringifyJsonField(raw.layoutMergeBboxesMode)
  }

  return out
}

/**
 * Builds the `ocr_config` object from `paddle` form values; returns null when nothing is set.
 */
export function paddleFormValuesToOcrConfig(
  paddle: Record<string, unknown> | undefined,
): Record<string, unknown> | null {
  if (!paddle || typeof paddle !== 'object') return null
  const out: Record<string, unknown> = {}

  if (typeof paddle.fileType === 'number' && !Number.isNaN(paddle.fileType)) {
    out.fileType = paddle.fileType
  }

  for (const k of TRISTATE_BOOL_KEYS) {
    const v = paddle[k]
    if (v === true || v === false) out[k] = v
  }

  const prompt = paddle.promptLabel
  if (typeof prompt === 'string' && prompt.trim().length > 0) {
    out.promptLabel = prompt.trim()
  }

  for (const k of OPTIONAL_NUMBER_KEYS) {
    const v = paddle[k]
    if (typeof v === 'number' && !Number.isNaN(v)) out[k] = v
  }

  const pm = paddle.prettifyMarkdown
  if (pm === true) out.prettifyMarkdown = true
  else if (pm === false) out.prettifyMarkdown = false

  const sfn = paddle.showFormulaNumber
  if (sfn === true) out.showFormulaNumber = true
  else if (sfn === false) out.showFormulaNumber = false

  for (const { apiKey, textKey } of JSON_TEXT_FIELDS) {
    const raw = paddle[textKey]
    if (typeof raw !== 'string' || !raw.trim()) continue
    const trimmed = raw.trim()
    try {
      out[apiKey] = JSON.parse(trimmed) as unknown
    } catch {
      throw new Error(`invalid_json:${apiKey}`)
    }
  }

  const mergeRaw = paddle.layoutMergeBboxesMode
  if (typeof mergeRaw === 'string' && mergeRaw.trim()) {
    const trimmed = mergeRaw.trim()
    try {
      out.layoutMergeBboxesMode = JSON.parse(trimmed) as unknown
    } catch {
      out.layoutMergeBboxesMode = trimmed
    }
  }

  return Object.keys(out).length > 0 ? out : null
}
