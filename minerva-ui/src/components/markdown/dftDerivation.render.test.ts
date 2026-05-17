import { describe, expect, it } from 'vitest'
import { unified } from 'unified'
import remarkParse from 'remark-parse'
import remarkRehype from 'remark-rehype'
import rehypeKatex from 'rehype-katex'
import { visit } from 'unist-util-visit'
import { MINERVA_MARKDOWN_REMARK_PLUGINS } from '@/components/markdown/markdownPlugins'
import { normalizeMarkdownForAgent } from '@/components/markdown/normalizeMarkdownMath'
import { DFT_DERIVATION_MARKDOWN } from '@/components/markdown/dftDerivation.fixture'

const MODEL_OVER_WRAPPED_DOLLARS = `#### $3.2 推导思路（连续信号的采样与截断）$

$DFT 的推导可以看作是对连续傅里叶变换（FT）进行**离散化**和**有限化**的结果。$

1. $**时域采样**：将连续信号 f(t) 乘以采样冲激串，时域相乘对应频域周期延拓。$
`

const ROTATION_FACTOR_LINE =
  '通常令旋转因子 $W_N = e^{-i \\frac{2\\pi}{N}}，则公式简化为 $X[k] = \\sum_{n=0}^{N-1} x[n] W_N^{kn}$。'

const USER_CASES_MARKDOWN = `**代数推导思路（更直观）：**
假设我们只关心傅里叶级数在基频 $\\omega_0 = \\frac{2\\pi}{NT}$（$T$为采样间隔）的整数倍上的频率分量。
将连续傅里叶变换的积分近似为黎曼和（积分变求和，$dt \\to T$）：

忽略常数比例因子 $T$（通常归一化处理），令 $x[n] = f(nT)$，$\\omega_0 = \\frac{2\\pi}{N}$（假设 $T=1$），即得到 DFT 公式。`

describe('DFT derivation markdown render', () => {
  it('fixes missing $ before CJK comma (rotation factor line)', () => {
    const out = normalizeMarkdownForAgent(ROTATION_FACTOR_LINE)
    expect(out).toContain(String.raw`$W_N = e^{-i \frac{2\pi}{N}}$，则公式简化为 $X[k]`)
    expect(out).not.toContain('\\text{则公式')
    const processor = unified().use(remarkParse).use(MINERVA_MARKDOWN_REMARK_PLUGINS)
    const mdast = processor.runSync(processor.parse(out))
    let sumMath = 0
    visit(mdast, 'inlineMath', (node) => {
      if (node.value.includes('\\sum')) sumMath++
    })
    expect(sumMath).toBe(1)
  })

  it('renders user cases 2 and 3 without literal \\text in prose', async () => {
    const md = normalizeMarkdownForAgent(USER_CASES_MARKDOWN)
    expect(md).not.toMatch(/\\text\{为采样/)
    const processor = unified()
      .use(remarkParse)
      .use(MINERVA_MARKDOWN_REMARK_PLUGINS)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeKatex, { output: 'html', strict: 'ignore', throwOnError: false })
    const hast = await processor.run(processor.parse(md))
    let katex = 0
    visit(hast, 'element', (node) => {
      if (node.tagName === 'span' && node.properties?.className?.includes?.('katex')) katex++
    })
    expect(katex).toBeGreaterThanOrEqual(4)
  })

  it('preprocess does not inject \\text{} into prose without math fences', () => {
    const out = normalizeMarkdownForAgent(DFT_DERIVATION_MARKDOWN)
    expect(out).toContain('DFT 的推导可以看作')
    expect(out).not.toMatch(/DFT \\text\{的推导/)
    const intro = out.split('\n\n')[1]
    expect(intro).not.toContain('\\text{')
  })

  it('parses inline math in list items and paragraphs', () => {
    const md = normalizeMarkdownForAgent(DFT_DERIVATION_MARKDOWN)
    const processor = unified().use(remarkParse).use(MINERVA_MARKDOWN_REMARK_PLUGINS)
    const mdast = processor.runSync(processor.parse(md))

    let inlineMath = 0
    let textWithTextCmd = 0
    visit(mdast, 'inlineMath', () => {
      inlineMath++
    })
    visit(mdast, 'text', (node) => {
      if (node.value.includes('\\text{')) textWithTextCmd++
    })
    expect(inlineMath).toBeGreaterThanOrEqual(5)
    expect(textWithTextCmd).toBe(0)
  })

  it('unwraps model-style $...$ around CJK prose (avoids literal \\text{})', () => {
    const out = normalizeMarkdownForAgent(MODEL_OVER_WRAPPED_DOLLARS)
    expect(out).toContain('DFT 的推导可以看作')
    expect(out).not.toContain('\\text{的推导')
    expect(out).not.toMatch(/\$DFT /)
    expect(out).toContain('**时域采样**')
  })

  it('renders KaTeX in list items', async () => {
    const md = normalizeMarkdownForAgent(DFT_DERIVATION_MARKDOWN)
    const processor = unified()
      .use(remarkParse)
      .use(MINERVA_MARKDOWN_REMARK_PLUGINS)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeKatex, { output: 'html', strict: 'ignore', throwOnError: false })
    const hast = await processor.run(processor.parse(md))

    let katexInLi = 0
    visit(hast, 'element', (node, _i, parent) => {
      if (
        parent?.type === 'element' &&
        parent.tagName === 'li' &&
        node.tagName === 'span' &&
        Array.isArray(node.properties?.className) &&
        node.properties.className.includes('katex')
      ) {
        katexInLi++
      }
    })
    expect(katexInLi).toBeGreaterThanOrEqual(2)
  })
})
