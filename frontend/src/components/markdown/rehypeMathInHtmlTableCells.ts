/**
 * Promote ``$...$`` in raw HTML ``<td>`` / ``<th>`` text nodes to ``math-inline`` elements for rehype-katex.
 */
import type { Element, ElementContent, Root, Text } from 'hast'
import type { Plugin } from 'unified'
import { visit } from 'unist-util-visit'

/** Inline ``$...$`` inside a table cell text node (no nested ``$``). */
const INLINE_MATH_IN_TEXT_RE = /\$([^$\n]+?)\$/g

/**
 * Split one text node into prose + ``<code class="math-inline">`` children.
 */
function splitTextNodeIntoPhrasing(text: string): ElementContent[] {
  const out: ElementContent[] = []
  let last = 0
  INLINE_MATH_IN_TEXT_RE.lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = INLINE_MATH_IN_TEXT_RE.exec(text)) !== null) {
    if (match.index > last) {
      out.push({ type: 'text', value: text.slice(last, match.index) })
    }
    const value = match[1]
    out.push({
      type: 'element',
      tagName: 'code',
      properties: { className: ['language-math', 'math-inline'] },
      children: [{ type: 'text', value }],
    })
    last = match.index + match[0].length
  }

  if (last < text.length) {
    out.push({ type: 'text', value: text.slice(last) })
  }

  return out.length > 0 ? out : [{ type: 'text', value: text }]
}

/**
 * Replace text children that contain ``$...$`` with phrasing suitable for rehype-katex.
 */
function promoteMathInElementChildren(children: ElementContent[]): ElementContent[] {
  const out: ElementContent[] = []

  for (const child of children) {
    if (child.type !== 'text') {
      out.push(child)
      continue
    }
    const text = (child as Text).value
    if (!text.includes('$')) {
      out.push(child)
      continue
    }
    out.push(...splitTextNodeIntoPhrasing(text))
  }

  return out
}

/**
 * Rehype plugin: raw HTML table cells → ``math-inline`` code elements for KaTeX.
 */
export const rehypeMathInHtmlTableCells: Plugin<[], Root> = function rehypeMathInHtmlTableCells() {
  return (tree) => {
    visit(tree, 'element', (node: Element) => {
      if (node.tagName !== 'td' && node.tagName !== 'th') return
      node.children = promoteMathInElementChildren(node.children)
    })
  }
}
