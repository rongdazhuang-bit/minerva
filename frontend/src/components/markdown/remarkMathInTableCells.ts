/**
 * Re-parse GFM table cell phrasing so ``$...$`` becomes ``inlineMath`` nodes (micromark skips math in tables).
 */
import { fromMarkdown } from 'mdast-util-from-markdown'
import { mathFromMarkdown } from 'mdast-util-math'
import { math } from 'micromark-extension-math'
import { toString } from 'mdast-util-to-string'
import type { ListItem, Paragraph, PhrasingContent, Root, TableCell } from 'mdast'
import type { Plugin } from 'unified'
import { visit } from 'unist-util-visit'
import {
  balanceExtraClosingBraces,
  containsBareLatex,
  isProseLikeMathBody,
  wrapBareLatexSpansInPlainText,
  wrapCjkInMathBody,
} from '@/components/markdown/normalizeMarkdownMath'

/** Apply KaTeX-oriented fixes to a TeX fragment before render. */
function normalizeMathValue(value: string): string {
  return wrapCjkInMathBody(balanceExtraClosingBraces(value))
}

/**
 * Flatten a fragment ``fromMarkdown`` tree to phrasing nodes (table cells / list paragraphs cannot hold ``paragraph`` blocks).
 */
function extractPhrasingChildren(tree: Root): PhrasingContent[] {
  const out: PhrasingContent[] = []
  for (const block of tree.children) {
    if (block.type === 'paragraph' || block.type === 'heading') {
      out.push(...block.children)
    }
  }
  return out
}

/**
 * Parse one phrasing fragment with math support (single line; newlines folded to spaces).
 */
function parsePhrasingWithMath(source: string): PhrasingContent[] {
  const inlineSource = source.replace(/\s*\n+\s*/g, ' ').trim()
  if (!inlineSource) return []

  const tree = fromMarkdown(inlineSource, {
    extensions: [math({ singleDollarTextMath: true })],
    mdastExtensions: [mathFromMarkdown()],
  })

  const phrasing = extractPhrasingChildren(tree)
  if (
    phrasing.length === 1 &&
    phrasing[0].type === 'inlineMath' &&
    isProseLikeMathBody(phrasing[0].value)
  ) {
    return [{ type: 'text', value: phrasing[0].value }]
  }

  visit(tree, 'inlineMath', (node) => {
    if (!isProseLikeMathBody(node.value)) {
      node.value = normalizeMathValue(node.value)
    }
  })
  visit(tree, 'math', (node) => {
    node.value = normalizeMathValue(node.value)
  })

  return extractPhrasingChildren(tree)
}

function parseTableCellPhrasing(source: string): TableCell['children'] {
  return parsePhrasingWithMath(source) as TableCell['children']
}

/**
 * Whether the cell is a single raw text node (typical LLM table output before math re-parse).
 */
function isPlainTextTableCell(cell: TableCell): cell is TableCell & { children: [{ type: 'text'; value: string }] } {
  return cell.children.length === 1 && cell.children[0]?.type === 'text'
}

/** Whether ``paragraph`` is a single raw text node (before math re-parse). */
function isPlainTextParagraph(
  node: Paragraph,
): node is Paragraph & { children: [{ type: 'text'; value: string }] } {
  return node.children.length === 1 && node.children[0]?.type === 'text'
}

/**
 * Remark plugin: inject ``inlineMath`` / ``math`` inside GFM table cells and list item paragraphs.
 */
export const remarkMathInTableCells: Plugin<[], Root> = function remarkMathInTableCells() {
  return (tree) => {
    visit(tree, 'tableCell', (cell) => {
      const source = isPlainTextTableCell(cell) ? cell.children[0].value : toString(cell)
      if (!source.includes('$') && !containsBareLatex(source)) return
      if (!isPlainTextTableCell(cell)) return

      const prepared = source.includes('$') ? source.trim() : wrapBareLatexSpansInPlainText(source.trim())
      ;(cell as TableCell).children = parseTableCellPhrasing(prepared)
    })

    visit(tree, 'listItem', (item: ListItem) => {
      visit(item, 'paragraph', (paragraph) => {
        if (!isPlainTextParagraph(paragraph)) return
        const source = paragraph.children[0].value
        if (!source.includes('$')) return
        ;(paragraph as Paragraph).children = parsePhrasingWithMath(
          source.trim(),
        ) as Paragraph['children']
      })
    })
  }
}
