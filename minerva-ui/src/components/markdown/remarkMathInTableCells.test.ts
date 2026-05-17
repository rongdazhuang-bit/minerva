import { describe, expect, it } from 'vitest'
import { unified } from 'unified'
import remarkParse from 'remark-parse'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import remarkRehype from 'remark-rehype'
import rehypeKatex from 'rehype-katex'
import { visit } from 'unist-util-visit'
import { MINERVA_MARKDOWN_REMARK_PLUGINS } from '@/components/markdown/markdownPlugins'
import { normalizeMarkdownForAgent } from '@/components/markdown/normalizeMarkdownMath'

const fourierTable = `### 总结

| 变换类型 | 信号特征 | 核心公式 (正变换) | 物理意义 |
| :--- | :--- | :--- | :--- |
| **傅里叶级数 (FS)** | 连续、周期 | $\\int f(t) e^{-in\\omega_0 t} dt$ | 周期信号 = 离散频率的谐波叠加 |
| **傅里叶变换 (FT)** | 连续、非周期 | $\\int_{-\\infty}^{\\infty} f(t) e^{-i\\omega t} dt$ | 非周期信号 = 连续频率密度谱 |`

describe('remarkMathInTableCells', () => {
  it('creates inlineMath nodes inside table cells', () => {
    const processor = unified().use(remarkParse).use(MINERVA_MARKDOWN_REMARK_PLUGINS)
    const mdast = processor.runSync(processor.parse(fourierTable))

    let inlineMathInTable = 0
    let textWithBackslashText = 0
    visit(mdast, 'tableCell', (cell) => {
      visit(cell, 'inlineMath', () => {
        inlineMathInTable++
      })
      visit(cell, 'text', (node) => {
        if (node.value.includes('\\text{')) textWithBackslashText++
      })
    })

    expect(inlineMathInTable).toBeGreaterThanOrEqual(2)
    expect(textWithBackslashText).toBe(0)
  })

  it('renders KaTeX for formula cells after full rehype pipeline', async () => {
    const md = normalizeMarkdownForAgent(fourierTable)
    const processor = unified()
      .use(remarkParse)
      .use(MINERVA_MARKDOWN_REMARK_PLUGINS)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeKatex, { output: 'html', strict: 'ignore', throwOnError: false })
    const hast = await processor.run(processor.parse(md))

    let katexInTable = 0
    visit(hast, 'element', (node, index, parent) => {
      if (
        parent &&
        parent.type === 'element' &&
        parent.tagName === 'td' &&
        node.tagName === 'span' &&
        Array.isArray(node.properties?.className) &&
        node.properties.className.includes('katex')
      ) {
        katexInTable++
      }
    })
    expect(katexInTable).toBeGreaterThanOrEqual(2)
  })
})
