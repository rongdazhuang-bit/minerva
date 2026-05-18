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

/** Stable synthetic node id for edges that target bare CJK/words (e.g. ``F4 -.-> 全部组件``). */
function syntheticMermaidNodeId(label: string): string {
  const slug = label
    .trim()
    .replace(/\s+/g, '_')
    .replace(/[^\w\u4e00-\u9fff]/g, '')
    .slice(0, 28)
  return `_mn_${slug || 'node'}`
}

/**
 * Fix common model-generated Mermaid syntax errors (unclosed quotes, bare edge targets).
 */
export function repairMermaidSyntaxLines(source: string): string {
  return source
    .split('\n')
    .map((line) => {
      let out = line

      const unclosedQuoted = /^(\s*)([A-Za-z][\w]*)\["([^"\n]+)\]\s*$/.exec(out)
      if (unclosedQuoted) {
        const [, indent, id, label] = unclosedQuoted
        out = `${indent}${id}["${label}"]`
      }

      const quotedLabel = /^(\s*)([A-Za-z][\w]*)\["([\s\S]*)"\]\s*$/.exec(out)
      if (quotedLabel) {
        const [, indent, id, label] = quotedLabel
        let fixed = label
        const opens = (fixed.match(/\(/g) ?? []).length
        const closes = (fixed.match(/\)/g) ?? []).length
        if (opens > closes) {
          fixed += ')'.repeat(opens - closes)
        }
        out = `${indent}${id}["${fixed}"]`
      }

      const edgeBare = /^(\s*)([A-Za-z][\w]*)\s+(-\.->|--)\s+([\u4e00-\u9fff][\u4e00-\u9fff\w\s/]+)\s*$/.exec(
        out,
      )
      if (edgeBare) {
        const [, indent, from, arrow, target] = edgeBare
        const label = target.trim()
        const nid = syntheticMermaidNodeId(label)
        out = `${indent}${from} ${arrow} ${nid}["${label}"]`
      }

      return out
    })
    .join('\n')
}

/**
 * Sanitize Mermaid source immediately before ``mermaid.render`` (orphan lines + HTML breaks).
 */
export function normalizeMermaidSourceForRender(source: string): string {
  const withoutOrphans = source
    .split('\n')
    .filter((line) => !ORPHAN_MERMAID_NODE_TAIL.test(line))
    .join('\n')
  return normalizeMermaidHtmlLineBreaks(repairMermaidSyntaxLines(withoutOrphans))
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
