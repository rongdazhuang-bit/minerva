import { prepareMarkdownFencedDiagrams } from '@/components/markdown/normalizeMarkdownFences'
import { isPlainTextFenceLanguage } from '@/components/markdown/plainTextMathBlock'
import {
  applyOcrMarkdownImagePlaceholders,
  normalizeDisplayMathFencesForRemarkMath,
  normalizeLooseInlineMathDelimiters,
  promoteInlineMathContainingTagToDisplay,
} from '@/features/file-ocr/applyOcrMarkdownImagePlaceholders'

/** CJK unified ideographs (basic block + ext A) for ``\\text{}`` wrapping in math. */
const CJK_RUN_RE = /^[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+/

/** Typical LaTeX commands in real formulas (not model prose wrongly wrapped in ``$...$``). */
const LATEX_MATH_COMMAND_RE =
  /\\(?:dfrac|tfrac|frac|sum|int|prod|lim|sqrt|omega|pi|alpha|beta|gamma|cdot|times|to|infty|partial|mathbf|mathrm|left|right|begin|end|vec|Rightarrow|quad)\b/

/** Parenthesized TeX that models often emit without ``$`` delimiters. */
const BARE_TEX_IN_PARENS_RE = /([（(])\s*(\\[a-zA-Z][^）)\n]*?)\s*([）)])/g

/** Parenthesized unit/math fragments without a leading ``\\`` (e.g. ``(m/s^{2})``). */
const BARE_MATH_IN_PARENS_RE =
  /([（(])([^（)(]*(?:\^\{[^{}]+\}|\^[0-9A-Za-z./]+|_\{[^{}]+\}|_[0-9A-Za-z]|\\[a-zA-Z]+)[^（)]*?)([）)])/g

/** Superscripts, subscripts, or ``\\cmd`` outside ``$...$`` (OCR/HTML table cells). */
export const BARE_LATEX_INDICATOR_RE =
  /\^\{[^{}]+\}|\^[0-9A-Za-z./]|_\{[^{}]+\}|_[0-9A-Za-z]|\\[a-zA-Z]+/

/** Inline bare-TeX runs (e.g. ``m/s^{2}``, ``10\\pm0.5``) after parenthesized spans are wrapped. */
const BARE_LATEX_RUN_RE =
  /(?:\d+(?:[.,]\d+)?)?(?:[A-Za-z0-9./+-]*(?:\^\{[^{}]+\}|\^[0-9A-Za-z./]+|_\{[^{}]+\}|_[0-9A-Za-z]|\\[a-zA-Z]+(?:\{[^{}]*\})?)*)+/g

/** HTML ``<td>`` / ``<th>`` inner text (no nested tags). */
const HTML_TABLE_CELL_RE = /<t([dh])([^>]*)>([^<]*)<\/t\1>/gi

/** Strip redundant ``\\(...\\)`` wrappers inside a display-math body (already in math mode). */
const REDUNDANT_INLINE_BRACKET_IN_DISPLAY_RE = /\\\(([\s\S]*?)\\\)/g

/** Strip redundant nested ``\\[...\\]`` wrappers inside a display-math body (already in math mode). */
const REDUNDANT_NESTED_DISPLAY_BRACKET_PAIR_RE = /\\\[([\s\S]*?)\\\]/g

/**
 * Find the closing ``\\]`` for display math opened at ``openIndex`` (``\\[``), using depth counting
 * with a fallback to the last ``\\]`` when models emit only one closer for double ``\\[`` openers.
 */
function findDisplayBracketMathClose(text: string, openIndex: number): number {
  let depth = 1
  let i = openIndex + 2
  const n = text.length

  while (i < n) {
    if (text.startsWith('\\[', i)) {
      depth++
      i += 2
      continue
    }
    if (text.startsWith('\\]', i)) {
      depth--
      if (depth === 0) return i
      i += 2
      continue
    }
    i++
  }

  let last = -1
  for (let j = openIndex + 2; j < n; j++) {
    if (text.startsWith('\\]', j)) last = j
  }
  return last
}

/**
 * Models sometimes truncate a Christoffel product as ``- \\Gamma} - \\Gamma^...`` (extra ``}`` before the superscript).
 */
const STRAY_GAMMA_BRACE_BEFORE_SUP_RE = /-\s*\\Gamma\}\s*-\s*(\\Gamma\^)/g

/** ``\\partial\\_rho``-style subscripts (should be ``\\partial_\\rho``). */
const MIS_ESCAPED_SUBSCRIPT_RE = /(\\[a-zA-Z]+)\\_([a-zA-Z]+)/g

/** Orphan operators with ``\\null`` subscripts (invalid in KaTeX; common after σ→ρ substitution glitches). */
const ORPHAN_OPERATOR_NULL_SUB_RE = /(?:[+\-]\s*)?\\[a-zA-Z]+(?:_\{\\?null\}|_\\null)\b/g

/** Math fragments illegally nested inside ``\\text{...}`` (e.g. ``g^{\\mu\\nu}``). */
const EMBEDDED_MATH_IN_TEXT_FRAGMENT_RE = /[A-Za-z](?:\^\{[^{}]+\}|_\{[^{}]+\})+/g

/** Remove stray nested ``\\[`` / ``\\]`` delimiters from a display-math body. */
function stripRedundantNestedDisplayBrackets(body: string): string {
  let b = body.replace(REDUNDANT_NESTED_DISPLAY_BRACKET_PAIR_RE, '$1').trim()
  while (b.startsWith('\\[')) {
    b = b.slice(2).trimStart()
  }
  while (b.endsWith('\\]')) {
    b = b.slice(0, -2).trimEnd()
  }
  return b
}

/**
 * Split one ``\\text{...}`` inner string so embedded ``g^{...}`` / ``g_{...}`` render outside text mode.
 */
function rebuildTextCommandWithoutEmbeddedMath(inner: string): string {
  const matches = [...inner.matchAll(EMBEDDED_MATH_IN_TEXT_FRAGMENT_RE)]
  if (matches.length === 0) return `\\text{${inner}}`

  let out = ''
  let last = 0
  for (const m of matches) {
    const idx = m.index ?? 0
    if (idx > last) {
      out += `\\text{${inner.slice(last, idx)}}`
    }
    out += m[0]
    last = idx + m[0].length
  }
  if (last < inner.length) {
    out += `\\text{${inner.slice(last)}}`
  }
  return out
}

/**
 * Move ``g^{\\mu\\nu}``-style fragments out of ``\\text{...}`` (KaTeX text mode cannot nest math).
 */
export function repairEmbeddedMathInTextCommands(tex: string): string {
  let out = ''
  let i = 0
  const n = tex.length

  while (i < n) {
    if (tex.startsWith('\\text{', i)) {
      const start = i + '\\text{'.length
      let depth = 1
      let j = start
      while (j < n && depth > 0) {
        if (tex[j] === '{') depth++
        else if (tex[j] === '}') depth--
        j++
      }
      out += rebuildTextCommandWithoutEmbeddedMath(tex.slice(start, j - 1))
      i = j
      continue
    }
    out += tex[i]
    i++
  }

  return out
}

/** Shared KaTeX-oriented repairs for inline and display math bodies. */
export function repairMathBody(tex: string): string {
  const stripped = tex
    .replace(STRAY_GAMMA_BRACE_BEFORE_SUP_RE, '- $1')
    .replace(MIS_ESCAPED_SUBSCRIPT_RE, '$1_{$2}')
    .replace(ORPHAN_OPERATOR_NULL_SUB_RE, '')
    .replace(/\\[a-zA-Z]+(?:_\{\\?null\}|_\\null)\b/g, '')
  return wrapCjkInMathBody(balanceExtraClosingBraces(repairEmbeddedMathInTextCommands(stripped)))
}

/**
 * Repair common display-math typos (stray braces, CJK in ``\\text{}``) before KaTeX.
 */
export function repairDisplayMathBody(body: string): string {
  const trimmed = body.trim()
  if (!trimmed) return trimmed
  return repairMathBody(trimmed)
}

/** Rewrite a ``$$...$$`` inner span; preserve padding when no repair is needed. */
function repairDisplayMathFenceBody(rawBody: string): string {
  const trimmed = rawBody.trim()
  if (!trimmed) return rawBody
  const repaired = repairDisplayMathBody(trimmed)
  if (repaired === trimmed) return rawBody
  const lead = rawBody.match(/^\s*/)?.[0] ?? ''
  const trail = rawBody.match(/\s*$/)?.[0] ?? ''
  return `${lead}${repaired}${trail}`
}

/** Rewrite every ``$$...$$`` body with ``repairDisplayMathBody``. */
export function repairDisplayMathFencesInMarkdown(text: string): string {
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
      const multiline = /[\r\n]/.test(rawBody)
      const repaired = repairDisplayMathFenceBody(rawBody)
      out += multiline ? `$$\n${repaired.trim()}\n$$` : `$$${repaired}$$`
      i = closeBlock + 2
      continue
    }

    out += text[i]
    i++
  }

  return out
}

/** Bare ``\\text{...}`` outside ``$`` / ``\\(...\\)`` (models often omit math fences). */
const BARE_LATEX_TEXT_CMD_RE = /\\text\{([^{}]*)\}/g

/**
 * End index of an inline ``\\(...\\)`` body (exclusive); stops before nested ``\\(``, ``\\)``, or ``\\，``/``\\,`` prose.
 */
function findInlineBracketBodyEnd(text: string, bodyStart: number): number {
  let j = bodyStart
  const n = text.length

  while (j < n) {
    if (text.startsWith('\\)', j) || text.startsWith('\\(', j)) {
      return j
    }
    if (text[j] === '\\' && j + 1 < n) {
      const next = text[j + 1]
      if (next === '，') {
        const after = text[j + 2] ?? ''
        if (after === '\\') {
          j++
          continue
        }
        if (after === '' || /\s/.test(after) || /[\u4e00-\u9fff]/.test(after)) {
          return j
        }
      }
      if (next === ',') {
        const after = text[j + 2] ?? ''
        if (after === '\\') {
          j++
          continue
        }
        if (after === '' || /\s/.test(after) || /[\u4e00-\u9fff]/.test(after)) {
          return j
        }
      }
    }
    j++
  }
  return n
}

/**
 * Wrap bare ``\\text{...}`` spans in ``$...$`` when not already inside math delimiters.
 */
export function wrapBareLatexTextCommands(text: string): string {
  return mapOutsideDisplayMathFences(text, (chunk) =>
    mapOutsideInlineMathFences(chunk, (prose) =>
      prose.replace(BARE_LATEX_TEXT_CMD_RE, (_match, inner: string) => `$\\text{${inner}}$`),
    ),
  )
}

/**
 * Convert LaTeX-style ``\\[...\\]`` / ``\\(...\\)`` delimiters to remark-math ``$$`` / ``$`` fences.
 */
export function convertLatexBracketMathDelimiters(text: string): string {
  let out = ''
  let i = 0
  const n = text.length

  const emitBracketMathBody = (rawBody: string) => {
    const body = rawBody.trim().replace(/\\，/g, '\\,')
    if (!body) return
    out += `$${repairMathBody(body)}$`
  }

  while (i < n) {
    if (text.startsWith('\\[', i)) {
      const close = findDisplayBracketMathClose(text, i)
      if (close === -1) {
        out += text.slice(i)
        break
      }
      const rawBody = text.slice(i + 2, close)
      const body = repairDisplayMathBody(
        stripRedundantNestedDisplayBrackets(
          rawBody.replace(REDUNDANT_INLINE_BRACKET_IN_DISPLAY_RE, '$1'),
        ),
      )
      out += body ? `$$\n${body}\n$$` : '$$\n$$'
      i = close + 2
      continue
    }

    if (text.startsWith('\\(', i)) {
      const bodyStart = i + 2
      const end = findInlineBracketBodyEnd(text, bodyStart)
      emitBracketMathBody(text.slice(bodyStart, end))
      if (end < n && text.startsWith('\\)', end)) {
        i = end + 2
        continue
      }
      if (end < n && text.startsWith('\\(', end)) {
        i = end
        continue
      }
      if (end < n && text[end] === '\\' && text[end + 1] === '，') {
        out += '，'
        i = end + 2
        continue
      }
      if (end < n && text[end] === '\\' && text[end + 1] === ',') {
        const after = text[end + 2] ?? ''
        if (after !== '\\') {
          out += ','
          i = end + 2
          continue
        }
      }
      i = end
      continue
    }

    out += text[i]
    i++
  }

  return out
}

/** ``T \\to \\infty`` / ``T → ∞`` inside bold without ``$`` (models often omit fences). */
const BARE_ARROW_LIMIT_IN_BOLD_RE =
  /[A-Za-z][A-Za-z0-9]*(?:_\{[^{}]+\}|_[A-Za-z0-9])?\s*(?:\\to|→)\s*(?:\\infty|∞)/

/** Normalize Unicode limits and tighten spaces for KaTeX. */
function normalizeBareLimitInBold(tex: string): string {
  return tex
    .replace(/→/g, '\\to ')
    .replace(/∞/g, '\\infty')
    .replace(/[ \t]{2,}/g, ' ')
    .trim()
}

/** Whether ``**...**`` is a short bare TeX fragment (e.g. ``**F(\\omega)**``) that must render outside strong. */
function isBareTexBoldBody(inner: string): boolean {
  const t = inner.trim()
  if (!t || t.length > 64) return false
  if (/[\u4e00-\u9fff]/.test(t) && !/\\[a-zA-Z]/.test(t)) return false
  if (/\\[a-zA-Z]+/.test(t)) return true
  if (/[A-Za-z]\s*\([^)]+\)/.test(t) && /[_^\\]/.test(t)) return true
  if (BARE_ARROW_LIMIT_IN_BOLD_RE.test(t) && !/[\u4e00-\u9fff]/.test(t)) return true
  return false
}

/**
 * Pull bare ``T \\to \\infty`` / ``T → ∞`` out of a bold body so remark-math can parse it.
 */
function rebuildBoldSegmentWithBareLimit(inner: string): string {
  const re = new RegExp(BARE_ARROW_LIMIT_IN_BOLD_RE.source, 'g')
  let result = ''
  let last = 0
  let found = false

  for (const m of inner.matchAll(re)) {
    found = true
    const idx = m.index ?? 0
    if (idx > last) {
      result += `**${inner.slice(last, idx)}**`
    }
    result += `$${normalizeBareLimitInBold(m[0])}$`
    last = idx + m[0].length
  }

  if (!found) return `**${inner}**`
  if (last < inner.length) {
    result += `**${inner.slice(last)}**`
  }
  return result
}

/**
 * Fix ``**label **T→∞`` where the model closed bold before the limit (math left as plain text).
 */
export function repairPrematureBoldCloseBeforeMath(text: string): string {
  let out = text.replace(
    /\*\*([^*\n]+?)\s*\*\*\s*(\$[^$\n]+\$)(?!\*\*)/g,
    '**$1** $2',
  )
  out = out.replace(
    /\*\*([^*\n]+?)\s*\*\*\s*([A-Za-z][A-Za-z0-9]*)\s*(?:\\to|→)\s*(?:\\infty|∞)/g,
    (_match, label: string, sym: string) =>
      `**${label.trim()}** $${normalizeBareLimitInBold(`${sym} \\to \\infty`)}$`,
  )
  return out
}

/** Bold + inline math normalization (premature-close repair + unwrap math from ``**``). */
export function normalizeBoldWithInlineMath(text: string): string {
  return repairPrematureBoldCloseBeforeMath(unwrapInlineMathFromBoldSpans(repairPrematureBoldCloseBeforeMath(text)))
}

/**
 * Rebuild a bold span so ``$...$`` / ``$$`` sit outside ``**`` (remark-math does not parse math inside strong).
 */
export function unwrapInlineMathFromBoldSpans(text: string): string {
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

    if (text.startsWith('**', i)) {
      const close = text.indexOf('**', i + 2)
      if (close === -1) {
        out += text.slice(i)
        break
      }
      const inner = text.slice(i + 2, close)
      const processed =
        inner.includes('\\(') || inner.includes('\\[')
          ? convertLatexBracketMathDelimiters(inner)
          : inner
      if (processed.includes('$')) {
        out += rebuildBoldSegmentWithExternalMath(processed)
        i = close + 2
        continue
      }
      if (BARE_ARROW_LIMIT_IN_BOLD_RE.test(processed)) {
        out += rebuildBoldSegmentWithBareLimit(processed)
        i = close + 2
        continue
      }
      if (isBareTexBoldBody(inner)) {
        const body = wrapCjkInMathBody(balanceExtraClosingBraces(inner.trim()))
        out += `$${body}$`
        i = close + 2
        continue
      }
      out += text.slice(i, close + 2)
      i = close + 2
      continue
    }

    out += text[i]
    i++
  }

  return out
}

/**
 * Split ``inner`` (bold body) into alternating ``**text**`` and bare ``$...$`` spans.
 */
function rebuildBoldSegmentWithExternalMath(inner: string): string {
  let segment = inner
  let result = ''

  while (segment.length > 0) {
    const open = indexOfUnescapedDollar(segment, 0)
    if (open < 0) {
      result += `**${segment}**`
      break
    }

    const close = indexOfUnescapedDollar(segment, open + 1)
    if (close < 0) {
      const prose = segment.slice(0, open)
      if (prose) result += `**${prose}**`
      result += segment.slice(open)
      break
    }

    const prose = segment.slice(0, open)
    if (prose) result += `**${prose}**`
    result += segment.slice(open, close + 1)
    segment = segment.slice(close + 1)
  }

  return result
}

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

/** Count CJK characters in ``s``. */
function countCjkChars(s: string): number {
  return (s.match(/[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]/g) ?? []).length
}

/**
 * Whether a ``$...$`` body is mostly natural-language prose (models often wrongly fence whole sentences).
 */
export function isProseLikeMathBody(body: string): boolean {
  const trimmed = body.trim()
  const len = trimmed.length
  if (len < 10) return false

  const cjk = countCjkChars(trimmed)
  if (cjk < 3) return false

  const hasLatex = LATEX_MATH_COMMAND_RE.test(trimmed)
  const hasSubSup = /[_^]/.test(trimmed)

  if (!hasLatex && !hasSubSup) return true

  if (hasLatex && cjk / len > 0.35 && len > 24) return true

  return false
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

/** CJK punctuation that often follows a model-truncated ``$...$`` before prose continues. */
const CJK_AFTER_MATH_PUNCT_RE = /[，。：；、]/

/**
 * Insert a missing ``$`` before CJK punctuation when a formula's closing fence was omitted (e.g. ``\\frac{\\pi}{N}}，则``).
 */
export function repairMissingInlineMathClosers(text: string): string {
  let out = ''
  let i = 0
  let inlineDepth = 0

  while (i < text.length) {
    if (text[i] === '$' && i + 1 < text.length && text[i + 1] === '$') {
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
      let backslashes = 0
      for (let j = i - 1; j >= 0 && text[j] === '\\'; j--) {
        backslashes++
      }
      if (backslashes % 2 === 0) {
        inlineDepth = inlineDepth === 0 ? 1 : 0
        out += '$'
        i++
        continue
      }
    }

    if (inlineDepth === 1 && CJK_AFTER_MATH_PUNCT_RE.test(text[i])) {
      const next = text[i + 1] ?? ''
      const prev = out[out.length - 1] ?? ''
      if (/[\u4e00-\u9fff]/.test(next) && /[}\)\]\w\d]/.test(prev)) {
        out += '$'
        inlineDepth = 0
      }
    }

    out += text[i]
    i++
  }

  return out
}

/**
 * Split a mis-paired ``$...$`` body at ``}}，中文`` so the TeX prefix and trailing prose separate.
 */
function trySplitMathBodyAtCjkContinuation(
  rawBody: string,
): { math: string; suffix: string } | null {
  const match = /^([\s\S]*?\})(\s*[，。：；、][\u4e00-\u9fff][\s\S]*)$/.exec(rawBody)
  if (!match) return null

  const math = match[1]
  let balance = 0
  for (const ch of math) {
    if (ch === '{') balance++
    else if (ch === '}') balance--
  }
  if (balance !== 0) return null
  if (isProseLikeMathBody(rawBody)) return null
  if (!LATEX_MATH_COMMAND_RE.test(math) && !/[_^=\\]/.test(math)) return null

  return { math, suffix: match[2] }
}

/**
 * Wrap ``(\\vec{...})`` / ``（\\vec{...}）`` fragments in ``$...$`` when the model omits math fences.
 */
export function wrapBareTexInParentheses(text: string): string {
  return mapOutsideInlineMathFences(text, (chunk) =>
    chunk.replace(BARE_TEX_IN_PARENS_RE, (match, open: string, tex: string, close: string) => {
      if (tex.includes('$')) return match
      const inner = wrapCjkInMathBody(balanceExtraClosingBraces(tex.trim()))
      return `${open}$${inner}$${close}`
    }),
  )
}

/**
 * Whether ``text`` contains TeX-like markup not already wrapped in ``$...$``.
 */
export function containsBareLatex(text: string): boolean {
  if (!text || text.includes('$')) return false
  return BARE_LATEX_INDICATOR_RE.test(text)
}

/** Wrap one bare-TeX fragment for remark-math / KaTeX. */
function wrapBareLatexFragment(fragment: string): string {
  const inner = wrapCjkInMathBody(balanceExtraClosingBraces(fragment.trim()))
  if (isProseLikeMathBody(inner)) return fragment
  return `$${inner}$`
}

/**
 * Wrap parenthesized and inline bare TeX (``(m/s^{2})``, ``10\\pm0.5``) in ``$...$``.
 */
export function wrapBareLatexSpansInPlainText(text: string): string {
  return mapOutsideInlineMathFences(text, (chunk) => {
    let out = chunk.replace(
      BARE_MATH_IN_PARENS_RE,
      (match, open: string, tex: string, close: string) => {
        if (tex.includes('$') || !BARE_LATEX_INDICATOR_RE.test(tex)) return match
        return `${open}${wrapBareLatexFragment(tex)}${close}`
      },
    )

    out = mapOutsideInlineMathFences(out, (segment) =>
      segment.replace(BARE_LATEX_RUN_RE, (run) => {
        if (!BARE_LATEX_INDICATOR_RE.test(run)) return run
        return wrapBareLatexFragment(run)
      }),
    )

    return out
  })
}

/**
 * Inject ``$...$`` around bare TeX inside HTML ``<td>`` / ``<th>`` cells (OCR Paddle tables).
 */
export function wrapBareLatexInHtmlTableCells(text: string): string {
  return text.replace(HTML_TABLE_CELL_RE, (full, tag: string, attrs: string, inner: string) => {
    const trimmed = inner.trim()
    if (!trimmed || !containsBareLatex(trimmed)) return full
    return `<t${tag}${attrs}>${wrapBareLatexSpansInPlainText(inner)}</t${tag}>`
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
      if (isProseLikeMathBody(rawBody)) {
        out += rawBody
        i = close + 1
        continue
      }

      const split = trySplitMathBodyAtCjkContinuation(rawBody)
      const mathPart = split?.math ?? rawBody
      const suffix = split?.suffix ?? ''

      const body = repairMathBody(mathPart)
      out += `$${body}$${suffix}`
      i = split ? Math.max(close, open + 1) : close + 1
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

/** Opening fence with optional info string and body (non-greedy close). */
const FENCED_BLOCK_WITH_INFO_RE = /^```([^\n]*)\n([\s\S]*?)```$/

/**
 * Apply ``transform`` only inside plaintext fenced code blocks (empty / text / plaintext lang).
 */
export function mapInsidePlainTextFencedCodeBlocks(
  text: string,
  transform: (body: string) => string,
): string {
  const parts = text.split(/(```[\s\S]*?```)/g)
  return parts
    .map((part, idx) => {
      if (idx % 2 === 0) return part
      const match = FENCED_BLOCK_WITH_INFO_RE.exec(part)
      if (!match) return part
      const info = match[1] ?? ''
      if (!isPlainTextFenceLanguage(info)) return part
      const body = match[2] ?? ''
      return `\`\`\`${info}\n${transform(body)}\`\`\``
    })
    .join('')
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

/**
 * Apply ``transform`` only outside single-dollar ``$...$`` spans (skips ``$$`` blocks).
 */
export function mapOutsideInlineMathFences(text: string, transform: (chunk: string) => string): string {
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
      const close = indexOfUnescapedDollar(text, open + 1)
      if (close < 0) {
        out += text.slice(open)
        break
      }
      out += text.slice(open, close + 1)
      i = close + 1
      continue
    }

    const nextInline = indexOfUnescapedDollar(text, i)
    const nextDisplay = text.indexOf('$$', i)
    let end = n
    if (nextInline >= 0) end = Math.min(end, nextInline)
    if (nextDisplay >= 0) end = Math.min(end, nextDisplay)
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

      if (/^\s{2,}\$\$/.test(cont)) {
        if (out[out.length - 1]?.trim() !== '') {
          out.push('')
        }
        const block: string[] = []
        if (/^\s*\$\$\s*$/.test(cont.trim()) && cont.trim() === '$$') {
          block.push('$$')
        } else {
          const sameLine = /^\s+\$\$(.*)$/.exec(cont)
          block.push(sameLine ? `$$${sameLine[1]}` : '$$')
        }
        let j = i + 1
        while (j < lines.length) {
          const lj = lines[j]
          if (/^\s*\$\$\s*$/.test(lj)) {
            block.push('$$')
            j++
            break
          }
          if (lj.trim() === '') {
            block.push('')
            j++
            continue
          }
          if (/^\s{2,}/.test(lj)) {
            block.push(lj.replace(/^\s+/, ''))
            j++
            continue
          }
          break
        }
        out.push(...block)
        i = j
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
 * Trim leading whitespace on ``$$`` fence lines (models often indent 1–3 spaces after prose).
 */
export function trimLeadingWhitespaceOnDisplayMathFenceLines(text: string): string {
  return text
    .split('\n')
    .map((line) => {
      const trimmed = line.trimStart()
      if (trimmed === '$$' || trimmed.startsWith('$$')) {
        return trimmed
      }
      return line
    })
    .join('\n')
}

/**
 * List items often indent ``$$``; GFM may treat 4+ spaces as code, 1–3 as broken flow math.
 */
export function unindentDisplayMathFenceLines(text: string): string {
  const lines = text.split('\n')
  const out: string[] = []

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const openMatch = /^(\s{1,})(\$\$)(.*)$/.exec(line)
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

  const fracCount = (trimmed.match(/\\(?:dfrac|tfrac|frac)\{/g) ?? []).length
  const textCount = (trimmed.match(/\\text\{/g) ?? []).length
  const eqCount = (trimmed.match(/=/g) ?? []).length

  if (fracCount >= 2 && textCount >= 4 && eqCount >= 2) return true

  if (fracCount >= 2 && textCount >= 2 && eqCount >= 1) return true

  if (textCount >= 1 && eqCount >= 1 && /\\times/.test(trimmed)) return true

  if (textCount >= 1 && eqCount >= 1 && trimmed.length >= 36) return true

  if (/\\quad/.test(trimmed) && (textCount >= 1 || fracCount >= 1)) return true

  if (/\\Rightarrow/.test(trimmed) && fracCount >= 1 && eqCount >= 1) return true

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

/** Whether ``line`` is a GFM pipe table row. */
function isGfmTableRow(line: string): boolean {
  const trimmed = line.trim()
  return trimmed.startsWith('|') && trimmed.indexOf('|', 1) !== -1
}

/** Decimal or integer on both sides of ``~`` (coordinate / numeric ranges, not GFM strikethrough). */
const NUMERIC_RANGE_TILDE_RE = /(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)/g

/**
 * Escape ``~`` between numbers so remark-gfm does not treat spans like ``116.22~116.55，23.42~23.66`` as strikethrough.
 */
export function escapeTildesInNumericRanges(text: string): string {
  return text.replace(NUMERIC_RANGE_TILDE_RE, '$1\\~$2')
}

/** Apply ``escapeTildesInNumericRanges`` outside ``$...$`` / ``$$...$$`` math fences. */
function escapeTildesInProseOutsideMath(text: string): string {
  return mapOutsideDisplayMathFences(text, (part) =>
    mapOutsideInlineMathFences(part, escapeTildesInNumericRanges),
  )
}

/**
 * Escape unescaped ``|`` inside a ``$...$`` / ``$$...$$`` fragment (GFM table column delimiter).
 */
function escapePipesInMathFragment(fragment: string): string {
  return fragment.replace(/(?<!\\)\|/g, '\\|')
}

/**
 * On one GFM table row, escape ``|`` inside math spans so ``|x[n]|`` does not split columns.
 */
export function escapePipesInTableRowMath(line: string): string {
  if (!isGfmTableRow(line) || !line.includes('$')) return line

  let out = ''
  let i = 0
  const n = line.length

  while (i < n) {
    if (line[i] === '$' && i + 1 < n && line[i + 1] === '$') {
      const close = line.indexOf('$$', i + 2)
      if (close < 0) {
        out += line.slice(i)
        break
      }
      out += escapePipesInMathFragment(line.slice(i, close + 2))
      i = close + 2
      continue
    }

    if (line[i] === '$') {
      const close = indexOfUnescapedDollar(line, i + 1)
      if (close < 0) {
        out += line.slice(i)
        break
      }
      out += escapePipesInMathFragment(line.slice(i, close + 1))
      i = close + 1
      continue
    }

    const nextInline = indexOfUnescapedDollar(line, i)
    const nextDisplay = line.indexOf('$$', i)
    let end = n
    if (nextInline >= 0) end = Math.min(end, nextInline)
    if (nextDisplay >= 0) end = Math.min(end, nextDisplay)
    out += line.slice(i, end)
    i = end
  }

  return out
}

/**
 * Apply ``transform`` only outside contiguous GFM table row blocks (table math uses ``remarkMathInTableCells``).
 */
export function mapOutsideGfmTableRows(text: string, transform: (chunk: string) => string): string {
  const lines = text.split('\n')
  const out: string[] = []
  let i = 0

  while (i < lines.length) {
    if (!isGfmTableRow(lines[i])) {
      const start = i
      while (i < lines.length && !isGfmTableRow(lines[i])) {
        i++
      }
      out.push(transform(lines.slice(start, i).join('\n')))
      continue
    }

    while (i < lines.length && isGfmTableRow(lines[i])) {
      out.push(escapePipesInTableRowMath(lines[i]))
      i++
    }
  }

  return out.join('\n')
}

/**
 * Agent chat math preprocessing (CJK in math, parenthesized TeX, loose ``$`` delimiters).
 */
export function normalizeMarkdownForAgent(markdown: string): string {
  const withPlainTextFenceMath = mapInsidePlainTextFencedCodeBlocks(
    prepareMarkdownFencedDiagrams(markdown),
    (body) =>
      normalizeInlineMathSpans(
        convertLatexBracketMathDelimiters(body),
      ),
  )
  return mapOutsideFencedCodeBlocks(withPlainTextFenceMath, (chunk) => {
    const withSafeNumericTildes = escapeTildesInProseOutsideMath(chunk)
    const withHtmlTableMath = wrapBareLatexInHtmlTableCells(withSafeNumericTildes)
    const base = ensureBlankLineBeforeDisplayMathFences(
      unindentDisplayMathFenceLines(
        unindentIndentedListContinuations(
          normalizeBoldWithInlineMath(
            repairDisplayMathFencesInMarkdown(
              wrapBareLatexTextCommands(convertLatexBracketMathDelimiters(withHtmlTableMath)),
            ),
          ),
        ),
      ),
    )
    return mapOutsideGfmTableRows(base, (nonTable) =>
      trimLeadingWhitespaceOnDisplayMathFenceLines(
        normalizeSelectiveDisplayMathFencesForRemarkMath(
          normalizeInlineMathSpans(
            mapOutsideDisplayMathFences(nonTable, (part) =>
              repairMissingInlineMathClosers(
                wrapBareTexInParentheses(normalizeLooseInlineMathDelimiters(part)),
              ),
            ),
          ),
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
  const withImages = applyOcrMarkdownImagePlaceholders(markdown, images)
  return normalizeDisplayMathFencesForRemarkMath(
    promoteInlineMathContainingTagToDisplay(
      normalizeLooseInlineMathDelimiters(
        unwrapInlineMathFromBoldSpans(
          wrapBareLatexTextCommands(
            convertLatexBracketMathDelimiters(
              wrapBareLatexInHtmlTableCells(prepareMarkdownFencedDiagrams(withImages)),
            ),
          ),
        ),
      ),
    ),
  )
}
