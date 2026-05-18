/**
 * Normalize Markdown fenced-code layout so GFM/remark recognize ``` blocks (e.g. inline `` ```mermaid ``).
 */

const OPENING_FENCE_ON_SAME_LINE =
  /^(\s{0,3})(.+?)(\s*)(```[\w#+.-]*)\s*$/

/** Orphan tail of a truncated Mermaid node definition such as ``DTO)"]``. */
const ORPHAN_MERMAID_NODE_TAIL = /^\s*[A-Za-z][\w]*\)"\]\s*$/

const MERMAID_FENCE_PATTERN = /(```mermaid\s*\n)([\s\S]*?)(```)/gi

/**
 * Insert a blank line before an opening fence when prose and `` ```lang `` share one line.
 */
export function splitInlineOpeningCodeFences(text: string): string {
  return text
    .split('\n')
    .map((line) => {
      const match = OPENING_FENCE_ON_SAME_LINE.exec(line)
      if (!match) return line
      const [, indent, before, space, fence] = match
      if (!before.trim()) return line
      return `${indent}${before}${space}\n\n${indent}${fence}`
    })
    .join('\n')
}

/**
 * Replace HTML line breaks in labels with Mermaid ``\\n`` (avoids invalid ``<br>`` in SVG foreignObject).
 */
export function normalizeMermaidHtmlLineBreaks(source: string): string {
  return source.replace(/<br\s*\/?>/gi, '\n')
}

/**
 * Sanitize Mermaid source immediately before ``mermaid.render`` (orphan lines + HTML breaks).
 */
export function normalizeMermaidSourceForRender(source: string): string {
  return normalizeMermaidHtmlLineBreaks(
    source
      .split('\n')
      .filter((line) => !ORPHAN_MERMAID_NODE_TAIL.test(line))
      .join('\n'),
  )
}

/**
 * Drop known-broken orphan lines inside `` ```mermaid `` blocks (common model truncation).
 */
function repairMermaidSource(body: string): string {
  return normalizeMermaidSourceForRender(body)
}

/**
 * Apply {@link repairMermaidSource} to every `` ```mermaid `` fenced block in ``text``.
 */
export function repairMermaidFencedBlocks(text: string): string {
  return text.replace(MERMAID_FENCE_PATTERN, (full, open, body, close) => {
    const repaired = repairMermaidSource(body)
    return repaired === body ? full : `${open}${repaired}${close}`
  })
}

/**
 * Prepare diagram fences for parsing: split inline openings, then sanitize Mermaid bodies.
 */
export function prepareMarkdownFencedDiagrams(text: string): string {
  return repairMermaidFencedBlocks(splitInlineOpeningCodeFences(text))
}
