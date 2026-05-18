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

  it('renders premature bold close **取极限 **T→∞', async () => {
    const raw = '2.  **取极限 **T→∞：'
    const md = normalizeMarkdownForAgent(raw)
    expect(md).toMatch(/\$T\\to \\infty\$| \$T \\to \\infty\$/)

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
    expect(katex).toBeGreaterThanOrEqual(1)
    expect(katexError).toBe(0)
  })

  it('renders numbered list limit **取极限 $T \\to \\infty$**', async () => {
    const raw = '2.  **取极限 $T \\to \\infty$**：'
    const md = normalizeMarkdownForAgent(raw)
    expect(md).toContain('$T \\to \\infty$')

    const processor = unified()
      .use(remarkParse)
      .use(MINERVA_MARKDOWN_REMARK_PLUGINS)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeKatex, { output: 'html', strict: 'ignore', throwOnError: false })

    const hast = await processor.run(processor.parse(md))
    let katexError = 0
    visit(hast, 'element', (node) => {
      const cls = node.properties?.className
      if (Array.isArray(cls) && cls.includes('katex-error')) katexError++
    })
    expect(katexError).toBe(0)
  })

  it('renders Ricci tensor with partial_\\null removed', async () => {
    const raw = String.raw`令 \(\sigma = \rho\)，得：

\[
R_{\mu\nu} = \partial_\rho \Gamma^{\rho}_{\mu\nu} - \partial_\null - \partial_\nu \Gamma^{\rho}_{\mu\rho} + \Gamma^{\rho}_{\lambda\rho} \Gamma^{\lambda}_{\mu\nu} - \Gamma^{\rho}_{\lambda\nu} \Gamma^{\lambda}_{\mu\rho}
\]`

    const md = normalizeMarkdownForAgent(raw)
    expect(md).not.toMatch(/\\null/)

    const processor = unified()
      .use(remarkParse)
      .use(MINERVA_MARKDOWN_REMARK_PLUGINS)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeKatex, { output: 'html', strict: 'ignore', throwOnError: false })

    const hast = await processor.run(processor.parse(md))
    let katexError = 0
    visit(hast, 'element', (node) => {
      const cls = node.properties?.className
      if (Array.isArray(cls) && cls.includes('katex-error')) katexError++
    })
    expect(katexError).toBe(0)
  })

  it('renders metric-only Einstein expansion with text-embedded g^{\\mu\\nu}', async () => {
    const raw = String.raw`合并后最完全的、仅含度规 \(g_{\mu\nu}\) 和其偏导的表达式可以写成（省略重复写入，仅示意结构）：

\[
\frac{1}{2} g^{\rho\lambda} \partial_\rho \partial_\mu g_{\lambda\nu} 
+ \frac{1}{2} g^{\rho\lambda} \partial_\rho \partial_\nu g_{\mu\lambda} 
- \frac{1}{2} g^{\rho\lambda} \partial_\rho \partial_\lambda g_{\mu\nu} 
+ \frac{1}{2} (\partial_\rho g^{\rho\lambda}) (g_{\lambda\nu,\mu} + g_{\mu\lambda,\nu} - g_{\mu\nu,\lambda})
- \frac{1}{2} g^{\rho\lambda} \partial_\nu \partial_\mu g_{\lambda\rho} 
- \frac{1}{2} g^{\rho\lambda} \partial_\nu \partial_\rho g_{\mu\lambda} 
+ \frac{1}{2} g^{\rho\lambda} \partial_\nu \partial_\lambda g_{\mu\rho} 
- \frac{1}{2} (\partial_\nu g^{\rho\lambda}) (g_{\lambda\rho,\mu} + g_{\mu\lambda,\rho} - g_{\mu\rho,\lambda})
+ \frac{1}{4} g^{\rho\sigma} g^{\lambda\tau} ( \partial_\lambda g_{\sigma\rho} + \partial_\rho g_{\lambda\sigma} - \partial_\sigma g_{\lambda\rho} ) ( \partial_\mu g_{\tau\nu} + \partial_\nu g_{\mu\tau} - \partial_\tau g_{\mu\nu} )
- \frac{1}{4} g^{\rho\sigma} g^{\lambda\tau} ( \partial_\lambda g_{\sigma\nu} + \partial_\nu g_{\lambda\sigma} - \partial_\sigma g_{\lambda\nu} ) ( \partial_\mu g_{\tau\rho} + \partial_\rho g_{\mu\tau} - \partial_\tau g_{\mu\rho} )
- \frac{1}{2} g_{\mu\nu} \cdot \text{(完整 R 展开，与上类似但多一个 g^{\mu\nu} 缩并)}
+ \Lambda g_{\mu\nu}
= \frac{8\pi G}{c^4} T_{\mu\nu}
\]`

    const md = normalizeMarkdownForAgent(raw)
    expect(md).toContain(String.raw`\text{ 缩并)}`)
    expect(md).toMatch(/g\^\{\\mu\\nu\}/)

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
    expect(katex).toBeGreaterThanOrEqual(2)
    expect(katexError).toBe(0)
  })

  it('renders Einstein field equation with underbrace and stray \\Gamma} typo', async () => {
    const raw = String.raw`将上述所有关系代入原方程，得到一个仅关于度规张量 \(g_{\mu\nu}\)（及其导数）和能量-动量张量 \(T_{\mu\nu}\) 的表达式：

\[
\underbrace{ \partial_\rho \Gamma^\rho_{\mu\nu} - \partial_\nu \Gamma^\rho_{\mu\rho} + \Gamma^\rho_{\lambda\rho} \Gamma^\lambda_{\mu\nu} - \Gamma} - \Gamma^\rho_{\lambda\nu} \Gamma^\lambda_{\mu\rho} }_{R_{\mu\nu} \text{ 的展开}} 
- \frac{1}{2} g_{\mu\nu} \underbrace{ \left[ g^{\sigma\tau} \left( \partial_\rho \Gamma^\rho_{\sigma\tau} - \partial_\tau \Gamma^\rho_{\sigma\rho} + \Gamma^\rho_{\lambda\rho} \Gamma^\lambda_{\sigma\tau} - \Gamma^\rho_{\lambda\tau} \Gamma^\lambda_{\sigma\rho} \right) \right] }_{R \text{ 的展开}} 
+ \Lambda g_{\mu\nu} = \frac{8\pi G}{c^4} T_{\mu\nu}
\]`

    const md = normalizeMarkdownForAgent(raw)
    expect(md).not.toContain('\\Gamma}')

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
    expect(katex).toBeGreaterThanOrEqual(2)
    expect(katexError).toBe(0)
  })

  it('renders double \\[ opener with single \\] closer (QCD Lagrangian style)', async () => {
    const raw = String.raw`其紧凑形式为：

\[
\[
\mathcal{L}_{\text{QCD}} = -\frac{1}{4} F_{\mu\nu}^a F^{a\mu\nu} + \sum_f \bar{\psi}_f (i\gamma^\mu D_\mu - m_f) \psi_f
\]`

    const md = normalizeMarkdownForAgent(raw)
    expect(md).not.toContain('\\[')
    expect(md).toMatch(/\$\$\s*\\mathcal\{L\}_\{\\text\{QCD\}\}/)

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
    expect(katex).toBeGreaterThanOrEqual(1)
    expect(katexError).toBe(0)
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
