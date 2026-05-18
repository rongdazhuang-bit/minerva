/** Supported Recharts plot kinds in Markdown `` ```chart `` fences. */
export type MarkdownChartType = 'line' | 'bar' | 'column' | 'pie' | 'area'

/** Normalized chart spec parsed from a fenced JSON block. */
export type MarkdownChartConfig = {
  type: MarkdownChartType
  data: Record<string, unknown>[]
  title?: string
  xField?: string
  yField?: string
  seriesField?: string
  angleField?: string
  colorField?: string
  height?: number
}

export type ParseMarkdownChartErrorCode =
  | 'invalid_json'
  | 'invalid_root'
  | 'unsupported_type'
  | 'empty_data'
  | 'invalid_data'
  | 'missing_fields'

export type ParseMarkdownChartResult =
  | { ok: true; config: MarkdownChartConfig }
  | { ok: false; error: ParseMarkdownChartErrorCode }

const CHART_TYPE_ALIASES: Record<string, MarkdownChartType> = {
  line: 'line',
  lines: 'line',
  bar: 'bar',
  bars: 'bar',
  horizontal: 'bar',
  horizontalbar: 'bar',
  column: 'column',
  columns: 'column',
  vertical: 'column',
  verticalbar: 'column',
  pie: 'pie',
  donut: 'pie',
  area: 'area',
}

const CHART_FENCE_LANGS = new Set(['chart', 'charts', 'antd-chart', 'ant-chart', 'plot'])

/** Whether a Markdown fence language tag should render as a chart block. */
export function isChartFenceLanguage(raw: string): boolean {
  return CHART_FENCE_LANGS.has(raw.toLowerCase().trim())
}

function inferCategoryAndValueKeys(
  row: Record<string, unknown>,
): { category?: string; value?: string } {
  const keys = Object.keys(row)
  if (keys.length === 0) return {}
  const numericKey = keys.find((k) => typeof row[k] === 'number')
  const categoryKey = keys.find((k) => k !== numericKey)
  return { category: categoryKey ?? keys[0], value: numericKey ?? keys[1] }
}

function inferCartesianFields(
  data: Record<string, unknown>[],
): Pick<MarkdownChartConfig, 'xField' | 'yField'> {
  const first = data[0]
  if (!first) return {}
  const { category, value } = inferCategoryAndValueKeys(first)
  return { xField: category, yField: value }
}

function inferPieFields(
  data: Record<string, unknown>[],
): Pick<MarkdownChartConfig, 'angleField' | 'colorField'> {
  const first = data[0]
  if (!first) return {}
  const { category, value } = inferCategoryAndValueKeys(first)
  return { colorField: category, angleField: value }
}

/**
 * Parse `` ```chart `` fenced JSON into a plot config for Recharts.
 * Expected shape: ``{ "type": "line", "data": [...], "xField": "...", "yField": "..." }``.
 */
export function parseMarkdownChartConfig(raw: string): ParseMarkdownChartResult {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw.trim())
  } catch {
    return { ok: false, error: 'invalid_json' }
  }
  if (parsed == null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { ok: false, error: 'invalid_root' }
  }

  const obj = parsed as Record<string, unknown>
  const typeKey = String(obj.type ?? 'line')
    .toLowerCase()
    .replace(/[\s_-]/g, '')
  const type = CHART_TYPE_ALIASES[typeKey]
  if (!type) {
    return { ok: false, error: 'unsupported_type' }
  }

  if (!Array.isArray(obj.data) || obj.data.length === 0) {
    return { ok: false, error: 'empty_data' }
  }

  const data = obj.data.filter(
    (row): row is Record<string, unknown> =>
      row != null && typeof row === 'object' && !Array.isArray(row),
  )
  if (data.length === 0) {
    return { ok: false, error: 'invalid_data' }
  }

  const cartesian = inferCartesianFields(data)
  const pie = inferPieFields(data)

  const config: MarkdownChartConfig = {
    type,
    data,
    title: typeof obj.title === 'string' ? obj.title.trim() || undefined : undefined,
    xField:
      typeof obj.xField === 'string'
        ? obj.xField
        : typeof obj.x === 'string'
          ? obj.x
          : cartesian.xField,
    yField:
      typeof obj.yField === 'string'
        ? obj.yField
        : typeof obj.y === 'string'
          ? obj.y
          : cartesian.yField,
    seriesField: typeof obj.seriesField === 'string' ? obj.seriesField : undefined,
    angleField:
      typeof obj.angleField === 'string'
        ? obj.angleField
        : typeof obj.value === 'string'
          ? obj.value
          : pie.angleField,
    colorField:
      typeof obj.colorField === 'string'
        ? obj.colorField
        : typeof obj.category === 'string'
          ? obj.category
          : pie.colorField,
    height:
      typeof obj.height === 'number' && Number.isFinite(obj.height) && obj.height > 0
        ? obj.height
        : undefined,
  }

  if (type === 'pie') {
    if (!config.angleField || !config.colorField) {
      return { ok: false, error: 'missing_fields' }
    }
  } else if (!config.xField || !config.yField) {
    return { ok: false, error: 'missing_fields' }
  }

  return { ok: true, config }
}
