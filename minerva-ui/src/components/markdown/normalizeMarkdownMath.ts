import {
  applyOcrMarkdownImagePlaceholders,
  normalizeDisplayMathFencesForRemarkMath,
  normalizeLooseInlineMathDelimiters,
  promoteInlineMathContainingTagToDisplay,
} from '@/features/file-ocr/applyOcrMarkdownImagePlaceholders'

/** CJK unified ideographs (basic block + ext A) for ``\\text{}`` wrapping in math. */
const CJK_RUN_RE = /^[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+/

/** Parenthesized TeX that models often emit without ``$`` delimiters. */
const BARE_TEX_IN_PARENS_RE = /([（(])\s*(\\[a-zA-Z][^）)\n]*?)\s*([）)])/g

/**
 * Return the index of the first unescaped ``$`` in ``s`` at or after ``from``, or ``-1``.
 */
function indexOfUnescapedDollar(s: string, from: number): number {
  for (let i = from; i < s.length; i++) {
    if (s[i] !== '$') continue
    let backslashes = 0
    for (let j = i - 1; j >= 0 && s[j] === '\\'; j--) {
      backslashes++
    }
    if (backslashes % 2 === 0) {
      return i
    }
  }
  return -1
}

/**
 * Strip trailing ``}`` when the fragment has more closers than openers (common LLM typo before ``$``).
 */
export function balanceExtraClosingBraces(tex: string): string {
  let balance = 0
  for (const ch of tex) {
    if (ch === '{') balance++
    else if (ch === '}') balance--
  }
  let out = tex
  while (balance < 0 && out.endsWith('}')) {
    out = out.slice(0, -1)
    balance++
  }
  return out
}

/**
 * Wrap bare CJK runs in ``\\text{...}`` so KaTeX can render subscripts like ``_{人\\to箱}``.
 */
export function wrapCjkInMathBody(body: string): string {
  let out = ''
  let i = 0
  const n = body.length

  while (i < n) {
    if (body.startsWith('\\text{', i)) {
      const start = i + '\\text{'.length
      let depth = 1
      let j = start
      while (j < n && depth > 0) {
        if (body[j] === '{') depth++
        else if (body[j] === '}') depth--
        j++
      }
      out += body.slice(i, j)
      i = j
      continue
    }

    const cjk = body.slice(i).match(CJK_RUN_RE)
    if (cjk) {
      out += `\\text{${cjk[0]}}`
      i += cjk[0].length
      continue
    }

    out += body[i]
    i++
  }

  return out
}

/**
 * Wrap ``(\\vec{...})`` / ``（\\vec{...}）`` fragments in ``$...$`` when the model omits math fences.
 */
export function wrapBareTexInParentheses(text: string): string {
  return text.replace(BARE_TEX_IN_PARENS_RE, (match, open: string, tex: string, close: string) => {
    if (tex.includes('$')) return match
    const inner = wrapCjkInMathBody(balanceExtraClosingBraces(tex.trim()))
    return `${open}$${inner}$${close}`
  })
}

/**
 * Normalize each ``$...$`` span: trim stray ``}``, wrap CJK for KaTeX.
 */
export function normalizeInlineMathSpans(text: string): string {
  let out = ''
  let i = 0
  const n = text.length

  while (i < n) {
    if (text[i] === '$' && i + 1 < n && text[i + 1] === '$') {
      const closeBlock = text.indexOf('$$', i + 2)
      if (closeBlock === -1) {
        out += text.slice(i)
        break
      }
      out += text.slice(i, closeBlock + 2)
      i = closeBlock + 2
      continue
    }

    if (text[i] === '$') {
      const open = i
      const bodyStart = open + 1
      const close = indexOfUnescapedDollar(text, bodyStart)
      if (close < 0) {
        out += text.slice(open)
        break
      }
      const rawBody = text.slice(bodyStart, close)
      const body = wrapCjkInMathBody(balanceExtraClosingBraces(rawBody))
      out += `$${body}$`
      i = close + 1
      continue
    }

    out += text[i]
    i++
  }

  return out
}

/**
 * Apply ``transform`` only outside Markdown fenced code blocks (``` ... ```).
 */
export function mapOutsideFencedCodeBlocks(text: string, transform: (chunk: string) => string): string {
  const parts = text.split(/(```[\s\S]*?```)/g)
  return parts.map((part, idx) => (idx % 2 === 1 ? part : transform(part))).join('')
}

/**
 * Apply ``transform`` only outside ``$$...$$`` spans (avoids nesting ``$`` inside display math).
 */
export function mapOutsideDisplayMathFences(text: string, transform: (chunk: string) => string): string {
  let out = ''
  let i = 0
  const n = text.length

  while (i < n) {
    if (text[i] === '$' && i + 1 < n && text[i + 1] === '$') {
      const closeBlock = text.indexOf('$$', i + 2)
      if (closeBlock === -1) {
        out += transform(text.slice(i))
        break
      }
      out += text.slice(i, closeBlock + 2)
      i = closeBlock + 2
      continue
    }

    const nextBlock = text.indexOf('$$', i)
    const end = nextBlock === -1 ? n : nextBlock
    if (end > i) {
      out += transform(text.slice(i, end))
    }
    i = end
  }

  return out
}

/** Whether ``line`` is a Markdown list marker (``*`` / ``-`` / ``1.``). */
function isListMarkerLine(line: string): boolean {
  return /^\s{0,3}([-*+]|\d+\.)\s+/.test(line)
}

/**
 * GFM parses lines indented 4+ spaces under a list item as a **code block**.
 *
 * Models often indent ``$$``, ``*(note)*``, and sub-bullets; strip one indent level so they render as math/prose.
 */
export function unindentIndentedListContinuations(text: string): string {
  const lines = text.split('\n')
  const out: string[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    out.push(line)

    if (!isListMarkerLine(line)) {
      i++
      continue
    }

    i++
    while (i < lines.length) {
      const cont = lines[i]
      if (cont.trim() === '') {
        out.push(cont)
        i++
        continue
      }

      const indented = /^(\s{4,})(.+)$/.exec(cont)
      if (!indented) {
        break
      }

      if (indented[2].trimStart().startsWith('```')) {
        break
      }

      out.push(indented[2])
      i++
    }
  }

  return out.join('\n')
}

/**
 * List items often indent ``$$`` by 4+ spaces; GFM then treats the line as code, not math.
 */
export function unindentDisplayMathFenceLines(text: string): string {
  const lines = text.split('\n')
  const out: string[] = []

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const openMatch = /^(\s{4,})(\$\$)(.*)$/.exec(line)
    if (!openMatch) {
      out.push(line)
      continue
    }

    const indent = openMatch[1]
    const afterOpen = openMatch[3]

    if (/\$\$\s*$/.test(afterOpen)) {
      out.push(`$$${afterOpen}`)
      continue
    }

    const block: string[] = [`$$${afterOpen}`]
    let j = i + 1
    while (j < lines.length) {
      const lj = lines[j]
      if (/^\s*\$\$\s*$/.test(lj)) {
        block.push('$$')
        j++
        break
      }
      if (lj.startsWith(indent) || lj.trim() === '') {
        block.push(lj.startsWith(indent) ? lj.slice(indent.length) : lj)
        j++
        continue
      }
      break
    }
    out.push(...block)
    i = j - 1
  }

  return out.join('\n')
}

/**
 * Insert a blank line before ``$$`` when it immediately follows prose so remark-math sees a flow block.
 */
export function ensureBlankLineBeforeDisplayMathFences(text: string): string {
  const lines = text.split('\n')
  const out: string[] = []

  for (const line of lines) {
    const trimmed = line.trim()
    const isClosingFenceOnly = trimmed === '$$'
    if (/^\s*\$\$/.test(line) && !isClosingFenceOnly) {
      const prev = out.length > 0 ? out[out.length - 1] : ''
      if (prev.trim() !== '' && !/^\s*\$\$/.test(prev)) {
        out.push('')
      }
    }
    out.push(line)
  }

  return out.join('\n')
}

/**
 * Whether a single-line ``$$...$$`` body should become flow display math for remark-math.
 */
function displayMathNeedsFlowFence(body: string): boolean {
  const trimmed = body.trim()
  if (!trimmed) return false
  if (/\\tag\*?/.test(trimmed) || /\\begin\{/.test(trimmed)) return true

  const fracCount = (trimmed.match(/\\frac\{/g) ?? []).length
  const textCount = (trimmed.match(/\\text\{/g) ?? []).length
  const eqCount = (trimmed.match(/=/g) ?? []).length

  if (fracCount >= 2 && textCount >= 4 && eqCount >= 2) return true

  if (fracCount >= 2 && textCount >= 2 && eqCount >= 1) return true

  if (textCount >= 1 && eqCount >= 1 && /\\times/.test(trimmed)) return true

  if (textCount >= 1 && eqCount >= 1 && trimmed.length >= 36) return true

  if (eqCount === 1 && /\s=\s/.test(trimmed) && /\\(gamma|rho|nu|mu|theta|phi|psi)\b/i.test(trimmed)) {
    return true
  }

  return false
}

/**
 * Promote only **single-line** ``$$...$$`` that need display mode; leave short in-flow ``$$`` as inline.
 *
 * ``micromark-extension-math`` treats ``$$\\n...\\n$$`` as flow math; a one-line ``$$...$$`` is otherwise
 * parsed as inline and long unit-style ``\\frac{\\text{...}}`` chains render poorly.
 */
export function normalizeSelectiveDisplayMathFencesForRemarkMath(text: string): string {
  let out = ''
  let i = 0
  const n = text.length

  while (i < n) {
    if (text[i] === '$' && i + 1 < n && text[i + 1] === '$') {
      const closeBlock = text.indexOf('$$', i + 2)
      if (closeBlock === -1) {
        out += text.slice(i)
        break
      }
      const rawBody = text.slice(i + 2, closeBlock)
      if (!/[\r\n]/.test(rawBody) && displayMathNeedsFlowFence(rawBody)) {
        out += `$$\n${rawBody.trim()}\n$$`
      } else {
        out += text.slice(i, closeBlock + 2)
      }
      i = closeBlock + 2
      continue
    }

    out += text[i]
    i += 1
  }

  return out
}

/**
 * Agent chat math preprocessing (CJK in math, parenthesized TeX, loose ``$`` delimiters).
 */
export function normalizeMarkdownForAgent(markdown: string): string {
  return mapOutsideFencedCodeBlocks(markdown, (chunk) => {
    const base = ensureBlankLineBeforeDisplayMathFences(
      unindentDisplayMathFenceLines(unindentIndentedListContinuations(chunk)),
    )
    return normalizeSelectiveDisplayMathFencesForRemarkMath(
      normalizeInlineMathSpans(
        mapOutsideDisplayMathFences(base, (part) =>
          wrapBareTexInParentheses(normalizeLooseInlineMathDelimiters(part)),
        ),
      ),
    )
  })
}

/** @deprecated Use ``normalizeMarkdownForAgent``. */
export const normalizeAgentChatMath = normalizeMarkdownForAgent

/**
 * OCR markdown math preprocessing (image placeholders, display fences, ``\\tag`` promotion).
 */
export function normalizeMarkdownForOcr(
  markdown: string | null | undefined,
  images?: Record<string, string> | null,
): string {
  return normalizeDisplayMathFencesForRemarkMath(
    promoteInlineMathContainingTagToDisplay(
      normalizeLooseInlineMathDelimiters(applyOcrMarkdownImagePlaceholders(markdown, images)),
    ),
  )
}
