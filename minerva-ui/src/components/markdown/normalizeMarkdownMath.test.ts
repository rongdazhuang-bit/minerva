import { renderToStaticMarkup } from 'react-dom/server'
import { createElement } from 'react'
import { describe, expect, it } from 'vitest'
import ReactMarkdown from 'react-markdown'

import {
  MINERVA_MARKDOWN_REHYPE_PLUGINS,
  MINERVA_MARKDOWN_REMARK_PLUGINS,
} from '@/components/markdown/markdownPlugins'
import {
  containsBareLatex,
  normalizeMarkdownForOcr,
  wrapBareLatexInHtmlTableCells,
  wrapBareLatexSpansInPlainText,
} from '@/components/markdown/normalizeMarkdownMath'

const VIBRATION_TABLE_HTML = `<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>试验项目</td><td style='text-align: center; word-wrap: break-word;'>试验内容</td><td style='text-align: center; word-wrap: break-word;'>参数</td></tr><tr><td rowspan="3">初始和最后振动响应检查</td><td style='text-align: center; word-wrap: break-word;'>频率范围/Hz</td><td style='text-align: center; word-wrap: break-word;'>10～150</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>扫频速度/(oct/min)</td><td style='text-align: center; word-wrap: break-word;'>≤1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>加速度/(m/s^{2})</td><td style='text-align: center; word-wrap: break-word;'>20</td></tr><tr><td rowspan="2">定频耐久性试验</td><td style='text-align: center; word-wrap: break-word;'>加速度/(m/s^{2})</td><td style='text-align: center; word-wrap: break-word;'>20</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>持续时间/min</td><td style='text-align: center; word-wrap: break-word;'>10\\pm0.5</td></tr><tr><td rowspan="4">扫频耐久试验</td><td style='text-align: center; word-wrap: break-word;'>频率范围/Hz</td><td style='text-align: center; word-wrap: break-word;'>10～150～10</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>加速度/(m/s^{2})</td><td style='text-align: center; word-wrap: break-word;'>20</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>扫频速度/(oct/min)</td><td style='text-align: center; word-wrap: break-word;'>≤1</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>循环次数</td><td style='text-align: center; word-wrap: break-word;'>10</td></tr><tr><td colspan="3">注：表中驱动振幅为峰值。</td></tr></table>`

function renderMinervaMarkdown(markdown: string): string {
  const normalized = normalizeMarkdownForOcr(markdown)
  return renderToStaticMarkup(
    createElement(ReactMarkdown, {
      remarkPlugins: MINERVA_MARKDOWN_REMARK_PLUGINS,
      rehypePlugins: MINERVA_MARKDOWN_REHYPE_PLUGINS,
    }, normalized),
  )
}

describe('wrapBareLatexSpansInPlainText', () => {
  it('detects superscripts and \\pm without $ delimiters', () => {
    expect(containsBareLatex('m/s^{2}')).toBe(true)
    expect(containsBareLatex('10\\pm0.5')).toBe(true)
    expect(containsBareLatex('10～150')).toBe(false)
  })

  it('wraps parenthesized units and pm expressions', () => {
    expect(wrapBareLatexSpansInPlainText('加速度/(m/s^{2})')).toContain('$m/s^{2}$')
    expect(wrapBareLatexSpansInPlainText('10\\pm0.5')).toBe('$10\\pm0.5$')
  })
})

describe('wrapBareLatexInHtmlTableCells', () => {
  it('injects $...$ into HTML table cells', () => {
    const out = wrapBareLatexInHtmlTableCells(VIBRATION_TABLE_HTML)
    expect(out).toContain('加速度/($m/s^{2}$)')
    expect(out).toContain('$10\\pm0.5$')
    expect(out).toContain('>10～150<')
  })
})

describe('normalizeMarkdownForOcr HTML table math', () => {
  it('renders KaTeX for m/s^{2} and \\pm inside HTML tables', () => {
    const html = renderMinervaMarkdown(`**表 2 振动适应性**\n\n${VIBRATION_TABLE_HTML}`)
    expect(html).toContain('class="katex"')
    expect(html).not.toContain('m/s^{2}')
    expect(html).not.toContain('\\pm0.5')
    expect(html).toMatch(/>\s*±\s*</)
  })
})
