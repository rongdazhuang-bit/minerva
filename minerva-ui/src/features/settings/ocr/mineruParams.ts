/**
 * Serializes MinerU self-hosted API options for persistence in `ocr_config` (snake_case keys).
 */

/** Dictionary item code for MinerU (TOOL_OCR). */
export const MINERU_OCR_TYPE_CODE = 'MINERU'

/** Default server-side output directory passed to MinerU ``/file_parse``. */
export const MINERU_DEFAULT_OUTPUT_DIR = './output'

/** MinerU parsing backend options (mineru-api). */
export const MINERU_BACKEND_OPTIONS = [
  'pipeline',
  'hybrid-auto-engine',
  'hybrid-http-client',
  'vlm-auto-engine',
  'vlm-http-client',
] as const

/** MinerU parse method options. */
export const MINERU_PARSE_METHOD_OPTIONS = ['auto', 'txt', 'ocr'] as const

/** Common OCR language hints for MinerU pipeline/hybrid backends. */
export const MINERU_LANG_OPTIONS = [
  'ch',
  'ch_server',
  'ch_lite',
  'en',
  'korean',
  'japan',
  'chinese_cht',
] as const

const BOOL_STORAGE_KEYS = [
  'formula_enable',
  'table_enable',
  'return_md',
  'return_middle_json',
  'return_model_output',
  'return_content_list',
  'return_images',
  'response_format_zip',
] as const

/** Maps form camelCase keys to persisted snake_case keys. */
const FORM_TO_STORAGE: Record<string, string> = {
  outputDir: 'output_dir',
  langList: 'lang_list',
  backend: 'backend',
  parseMethod: 'parse_method',
  formulaEnable: 'formula_enable',
  tableEnable: 'table_enable',
  serverUrl: 'server_url',
  returnMd: 'return_md',
  returnMiddleJson: 'return_middle_json',
  returnModelOutput: 'return_model_output',
  returnContentList: 'return_content_list',
  returnImages: 'return_images',
  responseFormatZip: 'response_format_zip',
  startPageId: 'start_page_id',
  endPageId: 'end_page_id',
}

const STORAGE_TO_FORM: Record<string, string> = Object.fromEntries(
  Object.entries(FORM_TO_STORAGE).map(([k, v]) => [v, k]),
)

/**
 * Default MinerU form slice aligned with backend ``FileParseFormOptions`` defaults.
 */
export function defaultMineruFormValues(): Record<string, unknown> {
  return {
    outputDir: MINERU_DEFAULT_OUTPUT_DIR,
    langList: ['ch'],
    backend: 'hybrid-auto-engine',
    parseMethod: 'auto',
    formulaEnable: true,
    tableEnable: true,
    serverUrl: '',
    returnMd: true,
    returnMiddleJson: true,
    returnModelOutput: false,
    returnContentList: false,
    returnImages: true,
    responseFormatZip: true,
    startPageId: 0,
    endPageId: undefined,
  }
}

function asBool(v: unknown): boolean | undefined {
  return v === true || v === false ? v : undefined
}

function asNonNegativeInt(v: unknown): number | undefined {
  if (typeof v !== 'number' || Number.isNaN(v) || !Number.isFinite(v)) return undefined
  const n = Math.floor(v)
  return n >= 0 ? n : undefined
}

/**
 * Maps stored `ocr_config` (snake_case) into form values under the `mineru` prefix.
 */
export function ocrConfigToMineruFormValues(
  raw: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  const out: Record<string, unknown> = { ...defaultMineruFormValues() }
  if (!raw || typeof raw !== 'object') {
    return out
  }

  const outputDir = raw.output_dir
  if (typeof outputDir === 'string' && outputDir.trim()) {
    out.outputDir = outputDir.trim()
  }

  const langs = raw.lang_list
  if (Array.isArray(langs)) {
    const list = langs.filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
    if (list.length > 0) {
      out.langList = list
    }
  }

  for (const [sk, fk] of [
    ['backend', 'backend'],
    ['parse_method', 'parseMethod'],
    ['server_url', 'serverUrl'],
  ] as const) {
    const v = raw[sk]
    if (typeof v === 'string') {
      out[fk] = v.trim()
    }
  }

  for (const sk of BOOL_STORAGE_KEYS) {
    const b = asBool(raw[sk])
    if (b !== undefined) {
      const fk = STORAGE_TO_FORM[sk]
      if (fk) out[fk] = b
    }
  }

  const start = asNonNegativeInt(raw.start_page_id)
  if (start !== undefined) {
    out.startPageId = start
  }

  const endRaw = raw.end_page_id
  if (endRaw === null) {
    out.endPageId = undefined
  } else {
    const end = asNonNegativeInt(endRaw)
    if (end !== undefined) {
      out.endPageId = end
    }
  }

  return out
}

/**
 * Builds `ocr_config` from `mineru` form values; always includes defaults for core fields.
 */
export function mineruFormValuesToOcrConfig(
  mineru: Record<string, unknown> | undefined,
): Record<string, unknown> | null {
  if (!mineru || typeof mineru !== 'object') return null

  const merged = { ...defaultMineruFormValues(), ...mineru }
  const out: Record<string, unknown> = {}

  const outputDir = merged.outputDir
  out.output_dir =
    typeof outputDir === 'string' && outputDir.trim()
      ? outputDir.trim()
      : MINERU_DEFAULT_OUTPUT_DIR

  const langs = merged.langList
  if (Array.isArray(langs) && langs.length > 0) {
    const list = langs
      .filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
      .filter((x, i, a) => a.indexOf(x) === i)
    out.lang_list = list.length > 0 ? list : ['ch']
  } else {
    out.lang_list = ['ch']
  }

  const backend = merged.backend
  out.backend =
    typeof backend === 'string' && backend.trim()
      ? backend.trim()
      : 'hybrid-auto-engine'

  const parseMethod = merged.parseMethod
  out.parse_method =
    typeof parseMethod === 'string' && parseMethod.trim() ? parseMethod.trim() : 'auto'

  const serverUrl = merged.serverUrl
  if (typeof serverUrl === 'string' && serverUrl.trim()) {
    out.server_url = serverUrl.trim()
  } else {
    out.server_url = null
  }

  for (const sk of BOOL_STORAGE_KEYS) {
    const fk = STORAGE_TO_FORM[sk]
    if (!fk) continue
    const b = asBool(merged[fk])
    if (b !== undefined) {
      out[sk] = b
    }
  }

  const start = asNonNegativeInt(merged.startPageId)
  out.start_page_id = start !== undefined ? start : 0

  const end = asNonNegativeInt(merged.endPageId)
  out.end_page_id = end !== undefined ? end : null

  return out
}
