import { describe, expect, it } from 'vitest'
import { fromMarkdown } from 'mdast-util-from-markdown'
import { mathFromMarkdown } from 'mdast-util-math'
import { math } from 'micromark-extension-math'
import { unified } from 'unified'
import remarkParse from 'remark-parse'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import { visit } from 'unist-util-visit'
import { remarkMathInTableCells } from '@/components/markdown/remarkMathInTableCells'
import { MINERVA_MARKDOWN_REMARK_PLUGINS } from '@/components/markdown/markdownPlugins'
import { normalizeMarkdownForAgent } from '@/components/markdown/normalizeMarkdownMath'

describe('remarkMathInTableCells mdast shape', () => {
  it('fromMarkdown wraps inline math in paragraph nodes (must flatten for table cells)', () => {
    const tree = fromMarkdown('$x^2$ plain', {
      extensions: [math({ singleDollarTextMath: true })],
      mdastExtensions: [mathFromMarkdown()],
    })
    expect(tree.children[0]?.type).toBe('paragraph')
  })

  it('does not leave paragraph nodes inside tableCell after plugin', () => {
    const md = '| a | $\\sum_{n=0}^{N-1} x[n]$ |\n| - | - |'
    const processor = unified().use(remarkParse).use(MINERVA_MARKDOWN_REMARK_PLUGINS)
    const mdast = processor.runSync(processor.parse(md))
    visit(mdast, 'tableCell', (cell) => {
      for (const child of cell.children) {
        expect(child.type).not.toBe('paragraph')
      }
    })
  })

  it('parses agent DFT content without stack overflow', () => {
    const md = normalizeMarkdownForAgent(`| 公式 |
| --- |
| $\\omega_0 = \\frac{2\\pi}{NT}$ |

1. $f(t)$ 采样
2. $N$ 点

通常令 $W_N = e^{-i \\frac{2\\pi}{N}}$，则 $X[k]=\\sum_n x[n]$。`)
    expect(() => {
      unified().use(remarkParse).use(MINERVA_MARKDOWN_REMARK_PLUGINS).runSync(
        unified().use(remarkParse).parse(md),
      )
    }).not.toThrow()
  })
})
