import { describe, expect, it } from 'vitest'
import {
  isChartFenceLanguage,
  parseMarkdownChartConfig,
} from '@/components/markdown/parseMarkdownChartConfig'

describe('isChartFenceLanguage', () => {
  it('recognizes chart fence tags', () => {
    expect(isChartFenceLanguage('chart')).toBe(true)
    expect(isChartFenceLanguage('antd-chart')).toBe(true)
    expect(isChartFenceLanguage('javascript')).toBe(false)
  })
})

describe('parseMarkdownChartConfig', () => {
  it('parses a line chart with inferred fields', () => {
    const r = parseMarkdownChartConfig(
      JSON.stringify({
        type: 'line',
        data: [
          { month: 'Jan', sales: 10 },
          { month: 'Feb', sales: 20 },
        ],
      }),
    )
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.config.type).toBe('line')
    expect(r.config.xField).toBe('month')
    expect(r.config.yField).toBe('sales')
  })

  it('parses a pie chart', () => {
    const r = parseMarkdownChartConfig(
      JSON.stringify({
        type: 'pie',
        data: [
          { kind: 'A', count: 30 },
          { kind: 'B', count: 70 },
        ],
      }),
    )
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.config.colorField).toBe('kind')
    expect(r.config.angleField).toBe('count')
  })

  it('rejects invalid json', () => {
    expect(parseMarkdownChartConfig('{ bad').ok).toBe(false)
  })
})
