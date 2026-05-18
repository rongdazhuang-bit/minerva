/**
 * Renders `` ```chart `` fenced JSON with Recharts (Line, Bar, Column, Pie, Area).
 */
import { Alert } from 'antd'
import { memo, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { randomChartColors } from '@/components/markdown/chartRandomColors'
import {
  parseMarkdownChartConfig,
  type MarkdownChartConfig,
} from '@/components/markdown/parseMarkdownChartConfig'

const DEFAULT_CHART_HEIGHT = 280

const GRID_STROKE = 'var(--minerva-border, #2a3f58)'

const TICK_STYLE = { fill: 'var(--minerva-ink-muted, #94a3b8)', fontSize: 11 }

const TOOLTIP_CONTENT_STYLE = {
  background: 'var(--minerva-surface, #1a2836)',
  borderColor: 'var(--minerva-border, #2a3f58)',
}

/** Plot area transparent; chat / message background shows through. */
const CHART_PLOT_STYLE = { background: 'transparent' } as const

const LEGEND_WRAPPER_STYLE = {
  fontSize: 12,
  color: 'var(--minerva-ink-muted, #94a3b8)',
} as const

/** Coerce chart metric values to numbers for Recharts. */
function toChartNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

/** Pivot long-format rows into wide format for multi-series Cartesian charts. */
function pivotSeriesData(
  data: Record<string, unknown>[],
  xField: string,
  yField: string,
  seriesField: string,
): { rows: Record<string, unknown>[]; seriesKeys: string[] } {
  const seriesSet = new Set<string>()
  const byX = new Map<string, Record<string, unknown>>()

  for (const row of data) {
    const xVal = row[xField]
    const xKey = String(xVal ?? '')
    const series = String(row[seriesField] ?? '')
    seriesSet.add(series)
    if (!byX.has(xKey)) {
      byX.set(xKey, { [xField]: xVal })
    }
    byX.get(xKey)![series] = toChartNumber(row[yField])
  }

  return { rows: [...byX.values()], seriesKeys: [...seriesSet] }
}

type RechartsCartesianProps = {
  config: MarkdownChartConfig
  width: number
  height: number
  colors: string[]
}

/** Shared axis, grid, tooltip, and legend for Cartesian Recharts. */
function CartesianExtras() {
  return (
    <>
      <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} opacity={0.45} />
      <Tooltip contentStyle={TOOLTIP_CONTENT_STYLE} />
      <Legend wrapperStyle={LEGEND_WRAPPER_STYLE} />
    </>
  )
}

/** Line chart (optional multi-series via ``seriesField``). */
function MarkdownLineChart({ config, width, height, colors }: RechartsCartesianProps) {
  const xField = config.xField!
  const yField = config.yField!
  const seriesField = config.seriesField

  const { chartData, seriesKeys } = useMemo(() => {
    if (seriesField) {
      const pivoted = pivotSeriesData(config.data, xField, yField, seriesField)
      return { chartData: pivoted.rows, seriesKeys: pivoted.seriesKeys }
    }
    return {
      chartData: config.data.map((row) => ({
        ...row,
        [yField]: toChartNumber(row[yField]),
      })),
      seriesKeys: [] as string[],
    }
  }, [config.data, seriesField, xField, yField])

  return (
    <LineChart
      width={width}
      height={height}
      data={chartData}
      style={CHART_PLOT_STYLE}
      margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
    >
      <CartesianExtras />
      <XAxis dataKey={xField} tick={TICK_STYLE} />
      <YAxis width={44} tick={TICK_STYLE} />
      {seriesField
        ? seriesKeys.map((key, i) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              name={key}
              stroke={colors[i % colors.length] ?? colors[0]}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          ))
        : (
            <Line
              type="monotone"
              dataKey={yField}
              stroke={colors[0]}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          )}
    </LineChart>
  )
}

/** Area chart (optional multi-series). */
function MarkdownAreaChart({ config, width, height, colors }: RechartsCartesianProps) {
  const xField = config.xField!
  const yField = config.yField!
  const seriesField = config.seriesField

  const { chartData, seriesKeys } = useMemo(() => {
    if (seriesField) {
      const pivoted = pivotSeriesData(config.data, xField, yField, seriesField)
      return { chartData: pivoted.rows, seriesKeys: pivoted.seriesKeys }
    }
    return {
      chartData: config.data.map((row) => ({
        ...row,
        [yField]: toChartNumber(row[yField]),
      })),
      seriesKeys: [] as string[],
    }
  }, [config.data, seriesField, xField, yField])

  return (
    <AreaChart
      width={width}
      height={height}
      data={chartData}
      style={CHART_PLOT_STYLE}
      margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
    >
      <CartesianExtras />
      <XAxis dataKey={xField} tick={TICK_STYLE} />
      <YAxis width={44} tick={TICK_STYLE} />
      {seriesField
        ? seriesKeys.map((key, i) => (
            <Area
              key={key}
              type="monotone"
              dataKey={key}
              name={key}
              stroke={colors[i % colors.length] ?? colors[0]}
              fill={colors[i % colors.length] ?? colors[0]}
              fillOpacity={0.25}
              isAnimationActive={false}
            />
          ))
        : (
            <Area
              type="monotone"
              dataKey={yField}
              stroke={colors[0]}
              fill={colors[0]}
              fillOpacity={0.25}
              isAnimationActive={false}
            />
          )}
    </AreaChart>
  )
}

/** Vertical column chart (``type: column``). */
function MarkdownColumnChart({ config, width, height, colors }: RechartsCartesianProps) {
  const xField = config.xField!
  const yField = config.yField!
  const seriesField = config.seriesField

  const { chartData, seriesKeys } = useMemo(() => {
    if (seriesField) {
      const pivoted = pivotSeriesData(config.data, xField, yField, seriesField)
      return { chartData: pivoted.rows, seriesKeys: pivoted.seriesKeys }
    }
    return {
      chartData: config.data.map((row) => ({
        ...row,
        [yField]: toChartNumber(row[yField]),
      })),
      seriesKeys: [] as string[],
    }
  }, [config.data, seriesField, xField, yField])

  return (
    <BarChart
      width={width}
      height={height}
      data={chartData}
      style={CHART_PLOT_STYLE}
      margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
    >
      <CartesianExtras />
      <XAxis dataKey={xField} tick={TICK_STYLE} />
      <YAxis width={44} tick={TICK_STYLE} />
      {seriesField
        ? seriesKeys.map((key, i) => (
            <Bar
              key={key}
              dataKey={key}
              name={key}
              fill={colors[i % colors.length] ?? colors[0]}
              isAnimationActive={false}
            />
          ))
        : (
            <Bar dataKey={yField} fill={colors[0]} isAnimationActive={false} />
          )}
    </BarChart>
  )
}

/** Horizontal bar chart (``type: bar``). */
function MarkdownBarChart({ config, width, height, colors }: RechartsCartesianProps) {
  const xField = config.xField!
  const yField = config.yField!
  const seriesField = config.seriesField

  const { chartData, seriesKeys } = useMemo(() => {
    if (seriesField) {
      const pivoted = pivotSeriesData(config.data, xField, yField, seriesField)
      return { chartData: pivoted.rows, seriesKeys: pivoted.seriesKeys }
    }
    return {
      chartData: config.data.map((row) => ({
        ...row,
        [yField]: toChartNumber(row[yField]),
      })),
      seriesKeys: [] as string[],
    }
  }, [config.data, seriesField, xField, yField])

  return (
    <BarChart
      layout="vertical"
      width={width}
      height={height}
      data={chartData}
      style={CHART_PLOT_STYLE}
      margin={{ top: 8, right: 16, left: 8, bottom: 8 }}
    >
      <CartesianExtras />
      <XAxis type="number" tick={TICK_STYLE} />
      <YAxis type="category" dataKey={xField} width={72} tick={TICK_STYLE} />
      {seriesField
        ? seriesKeys.map((key, i) => (
            <Bar
              key={key}
              dataKey={key}
              name={key}
              fill={colors[i % colors.length] ?? colors[0]}
              isAnimationActive={false}
            />
          ))
        : (
            <Bar dataKey={yField} fill={colors[0]} isAnimationActive={false} />
          )}
    </BarChart>
  )
}

/** Pie chart. */
function MarkdownPieChart({
  config,
  width,
  height,
  colors,
}: {
  config: MarkdownChartConfig
  width: number
  height: number
  colors: string[]
}) {
  const angleField = config.angleField!
  const colorField = config.colorField!
  const pieData = useMemo(
    () =>
      config.data.map((row) => ({
        ...row,
        [angleField]: toChartNumber(row[angleField]),
      })),
    [config.data, angleField],
  )

  return (
    <PieChart
      width={width}
      height={height}
      style={CHART_PLOT_STYLE}
      margin={{ top: 8, right: 16, left: 8, bottom: 8 }}
    >
      <Tooltip contentStyle={TOOLTIP_CONTENT_STYLE} />
      <Legend wrapperStyle={LEGEND_WRAPPER_STYLE} />
      <Pie
        data={pieData}
        dataKey={angleField}
        nameKey={colorField}
        cx="50%"
        cy="50%"
        outerRadius="72%"
        label={({ name, percent }) =>
          `${String(name ?? '')} ${((percent ?? 0) * 100).toFixed(0)}%`
        }
        isAnimationActive={false}
      >
        {pieData.map((_, i) => (
          <Cell key={i} fill={colors[i % colors.length] ?? colors[0]} />
        ))}
      </Pie>
    </PieChart>
  )
}

/** Series count for palette sizing. */
function chartSeriesCount(config: MarkdownChartConfig): number {
  if (config.type === 'pie') return config.data.length
  if (config.seriesField) {
    const keys = new Set<string>()
    for (const row of config.data) {
      keys.add(String(row[config.seriesField] ?? ''))
    }
    return Math.max(keys.size, 1)
  }
  return 1
}

/** Pick Recharts implementation for parsed chart config. */
function MarkdownRechartsPlot({
  config,
  chartKey,
  width,
  height,
}: {
  config: MarkdownChartConfig
  chartKey: string
  width: number
  height: number
}) {
  const colors = useMemo(
    () => randomChartColors(chartSeriesCount(config)),
    [chartKey],
  )

  switch (config.type) {
    case 'line':
      return (
        <MarkdownLineChart config={config} width={width} height={height} colors={colors} />
      )
    case 'area':
      return (
        <MarkdownAreaChart config={config} width={width} height={height} colors={colors} />
      )
    case 'column':
      return (
        <MarkdownColumnChart config={config} width={width} height={height} colors={colors} />
      )
    case 'bar':
      return <MarkdownBarChart config={config} width={width} height={height} colors={colors} />
    case 'pie':
      return <MarkdownPieChart config={config} width={width} height={height} colors={colors} />
    default:
      return null
  }
}

/** Recharts block for agent Markdown (JSON in `` ```chart `` fence). */
export const MarkdownChartBlock = memo(function MarkdownChartBlock({ code }: { code: string }) {
  const { t } = useTranslation()
  const hostRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const parsed = parseMarkdownChartConfig(code)

  useLayoutEffect(() => {
    const el = hostRef.current
    if (!el || !parsed.ok) return
    const measure = () => {
      const w = el.clientWidth
      if (w > 0) setWidth(w)
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [parsed.ok, code])

  if (!parsed.ok) {
    return (
      <Alert
        type="error"
        showIcon
        className="minerva-md-chart-error"
        message={t(`agents.chartError.${parsed.error}`)}
      />
    )
  }

  const { config } = parsed
  const height = config.height ?? DEFAULT_CHART_HEIGHT

  return (
    <figure className="minerva-md-chart" ref={hostRef}>
      {config.title ? (
        <figcaption className="minerva-md-chart-title">{config.title}</figcaption>
      ) : null}
      <div className="minerva-md-chart-plot" style={{ minHeight: height }}>
        {width > 0 ? (
          <MarkdownRechartsPlot config={config} chartKey={code} width={width} height={height} />
        ) : (
          <div className="minerva-md-chart-measure" style={{ height }} aria-hidden />
        )}
      </div>
    </figure>
  )
})
