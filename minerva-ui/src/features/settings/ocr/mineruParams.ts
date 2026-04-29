/**
 * Serializes MinerU API options for persistence in `ocr_config`（键名与 MinerU 接口一致：snake_case）。
 */

/** 数据字典 OCR 类型项编码（TOOL_OCR）— MinerU。 */
export const MINERU_OCR_TYPE_CODE = 'MINERU'

/** MinerU 支持的模型版本选项。 */
export const MINERU_MODEL_VERSION_OPTIONS = ['pipeline', 'vlm', 'MinerU-HTML'] as const

/** 额外导出格式（markdown、json 为默认，仅需配置 docx / html / latex）。 */
export const MINERU_EXTRA_FORMAT_OPTIONS = ['docx', 'html', 'latex'] as const

const SNAKE_BOOL_KEYS = ['is_ocr', 'enable_formula', 'enable_table', 'no_cache'] as const

/** 从表单 camelCase 读写的键与落库 snake_case 的对应。 */
const FORM_TO_STORAGE: Record<string, string> = {
  isOcr: 'is_ocr',
  enableFormula: 'enable_formula',
  enableTable: 'enable_table',
  language: 'language',
  dataId: 'data_id',
  callback: 'callback',
  seed: 'seed',
  extraFormats: 'extra_formats',
  pageRanges: 'page_ranges',
  modelVersion: 'model_version',
  noCache: 'no_cache',
  cacheTolerance: 'cache_tolerance',
}

const STORAGE_TO_FORM: Record<string, string> = Object.fromEntries(
  Object.entries(FORM_TO_STORAGE).map(([k, v]) => [v, k]),
)

/**
 * MinerU 表单项默认值（未填则提交时不写入对应键，交由服务端默认值）。
 */
export function defaultMineruFormValues(): Record<string, unknown> {
  return {}
}

function asBool(v: unknown): boolean | undefined {
  return v === true || v === false ? v : undefined
}

function asPositiveInt(v: unknown): number | undefined {
  if (typeof v !== 'number' || Number.isNaN(v) || !Number.isFinite(v)) return undefined
  const n = Math.floor(v)
  return n >= 0 ? n : undefined
}

/**
 * 将已保存的 `ocr_config`（snake_case）映射为表单 `mineru` 片段（camelCase）。
 */
export function ocrConfigToMineruFormValues(
  raw: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  const out: Record<string, unknown> = { ...defaultMineruFormValues() }
  if (!raw || typeof raw !== 'object') {
    return out
  }

  for (const snake of SNAKE_BOOL_KEYS) {
    const b = asBool(raw[snake])
    if (b !== undefined) {
      const fk = STORAGE_TO_FORM[snake]
      if (fk) out[fk] = b
    }
  }

  if (typeof raw.language === 'string' && raw.language.trim()) {
    out.language = raw.language.trim()
  }
  for (const [sk, fk] of [
    ['data_id', 'dataId'],
    ['callback', 'callback'],
    ['seed', 'seed'],
    ['page_ranges', 'pageRanges'],
    ['model_version', 'modelVersion'],
  ] as const) {
    const v = raw[sk]
    if (typeof v === 'string' && v.trim()) {
      out[fk] = v.trim()
    }
  }

  const xf = raw.extra_formats
  if (Array.isArray(xf)) {
    const list = xf.filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
    if (list.length > 0) {
      out.extraFormats = list
    }
  }

  const ct = asPositiveInt(raw.cache_tolerance)
  if (ct !== undefined) {
    out.cacheTolerance = ct
  }

  return out
}

/**
 * 从 `mineru` 表单构建 `ocr_config`；无有效字段时返回 `null`。
 */
export function mineruFormValuesToOcrConfig(
  mineru: Record<string, unknown> | undefined,
): Record<string, unknown> | null {
  if (!mineru || typeof mineru !== 'object') return null

  const out: Record<string, unknown> = {}

  const isOcr = asBool(mineru.isOcr)
  if (isOcr !== undefined) out.is_ocr = isOcr

  const ef = asBool(mineru.enableFormula)
  if (ef !== undefined) out.enable_formula = ef

  const et = asBool(mineru.enableTable)
  if (et !== undefined) out.enable_table = et

  const lang = mineru.language
  if (typeof lang === 'string' && lang.trim()) {
    out.language = lang.trim()
  }

  const dataId = mineru.dataId
  if (typeof dataId === 'string' && dataId.trim()) {
    out.data_id = dataId.trim().slice(0, 128)
  }

  const callback = mineru.callback
  if (typeof callback === 'string' && callback.trim()) {
    out.callback = callback.trim()
  }

  const seed = mineru.seed
  if (typeof seed === 'string' && seed.trim()) {
    out.seed = seed.trim().slice(0, 64)
  }

  const xf = mineru.extraFormats
  if (Array.isArray(xf) && xf.length > 0) {
    const allowed = new Set<string>(MINERU_EXTRA_FORMAT_OPTIONS)
    const list = xf
      .filter((x): x is string => typeof x === 'string' && allowed.has(x))
      .filter((x, i, a) => a.indexOf(x) === i)
    if (list.length > 0) {
      out.extra_formats = list
    }
  }

  const pageRanges = mineru.pageRanges
  if (typeof pageRanges === 'string' && pageRanges.trim()) {
    out.page_ranges = pageRanges.trim()
  }

  const mv = mineru.modelVersion
  if (typeof mv === 'string' && mv.trim()) {
    const t = mv.trim()
    if ((MINERU_MODEL_VERSION_OPTIONS as readonly string[]).includes(t)) {
      out.model_version = t
    }
  }

  const nc = asBool(mineru.noCache)
  if (nc !== undefined) out.no_cache = nc

  const ct = asPositiveInt(mineru.cacheTolerance)
  if (ct !== undefined) {
    out.cache_tolerance = ct
  }

  return Object.keys(out).length > 0 ? out : null
}
