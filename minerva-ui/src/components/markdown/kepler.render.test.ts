import { describe, expect, it } from 'vitest'
import { unified } from 'unified'
import remarkParse from 'remark-parse'
import remarkRehype from 'remark-rehype'
import rehypeKatex from 'rehype-katex'
import { visit } from 'unist-util-visit'
import { MINERVA_MARKDOWN_REMARK_PLUGINS } from '@/components/markdown/markdownPlugins'
import { KEPLER_MARKDOWN } from '@/components/markdown/kepler.fixture'
import { normalizeMarkdownForAgent } from '@/components/markdown/normalizeMarkdownMath'

describe('Kepler markdown sample', () => {
  it('normalizes display math fences and parses flow + inline math', () => {
    const md = normalizeMarkdownForAgent(KEPLER_MARKDOWN)
    expect(md).toMatch(/\$\$\nv_2 = \\sqrt/)
    expect(md).toMatch(/\$\$\nT\^2 = \\frac/)

    const remarkProcessor = unified().use(remarkParse).use(MINERVA_MARKDOWN_REMARK_PLUGINS)
    const mdast = remarkProcessor.runSync(remarkProcessor.parse(md))

    let flowMath = 0
    let inlineMath = 0
    visit(mdast, 'math', () => {
      flowMath++
    })
    visit(mdast, 'inlineMath', () => {
      inlineMath++
    })

    expect(flowMath).toBeGreaterThanOrEqual(2)
    expect(inlineMath).toBeGreaterThanOrEqual(4)
  })

  it('renders KaTeX for escape velocity and Kepler formulas', async () => {
    const md = normalizeMarkdownForAgent(KEPLER_MARKDOWN)
    const processor = unified()
      .use(remarkParse)
      .use(MINERVA_MARKDOWN_REMARK_PLUGINS)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeKatex, { output: 'html', strict: 'ignore', throwOnError: false })

    const hast = await processor.run(processor.parse(md))
    let katex = 0
    let katexError = 0
    visit(hast, 'element', (node) => {
      const cls = node.properties?.className
      if (!Array.isArray(cls)) return
      if (cls.includes('katex')) katex++
      if (cls.includes('katex-error')) katexError++
    })

    expect(katex).toBeGreaterThanOrEqual(6)
    expect(katexError).toBe(0)
  })

  it('unindents 2-space indented single-line display math after prose', () => {
    const raw = `由机械能守恒 $\\dfrac{1}{2}mv^2 - G\\dfrac{Mm}{R} = 0$ 得：
  $$v_2 = \\sqrt{\\frac{2GM}{R}} \\quad (\\text{地球约 } 11.2 \\, \\text{km/s})$$`

    const md = normalizeMarkdownForAgent(raw)
    const fenceLines = md.split('\n').filter((line) => line.trimStart().startsWith('$$'))
    expect(fenceLines.every((line) => line === line.trimStart())).toBe(true)
    expect(md).toMatch(/\$\$\nv_2 = \\sqrt/)

    const remarkProcessor = unified().use(remarkParse).use(MINERVA_MARKDOWN_REMARK_PLUGINS)
    const mdast = remarkProcessor.runSync(remarkProcessor.parse(md))
    let flowMath = 0
    visit(mdast, 'math', () => {
      flowMath++
    })
    expect(flowMath).toBeGreaterThanOrEqual(1)
  })

  it('unwraps inline math from bold in list item ($r$ 的定义)', () => {
    const raw = '4. **$r$ 的定义**：必须是两物体**质心**之间的距离。'
    const md = normalizeMarkdownForAgent(raw)
    expect(md).toMatch(/\$r\$\*\*.*定义\*\*/)

    const remarkProcessor = unified().use(remarkParse).use(MINERVA_MARKDOWN_REMARK_PLUGINS)
    const mdast = remarkProcessor.runSync(remarkProcessor.parse(md))
    let inlineInList = 0
    visit(mdast, 'listItem', (item) => {
      visit(item, 'inlineMath', (node) => {
        inlineInList++
        expect(node.value).toBe('r')
      })
    })
    expect(inlineInList).toBe(1)
  })
})
