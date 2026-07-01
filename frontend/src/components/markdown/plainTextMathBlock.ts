/** Helpers to detect and render KaTeX inside plaintext Markdown fenced code blocks. */
import katex from 'katex'
import {
  isProseLikeMathBody,
  repairMathBody,
} from '@/components/markdown/normalizeMarkdownMath'
import { normalizePrismLanguage } from '@/components/markdown/prismLanguages'

/** One prose or math fragment within a plaintext code block line. */
export type PlainTextMathSegment =
  | { type: 'text'; value: string }
  | { type: 'inline'; value: string }
  | { type: 'display'; value: string }

/** Inline ``$...$`` on one line (no nested ``$``). */
const INLINE_MATH_IN_LINE_RE = /\$([^$\n]+?)\$/g

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
 * Whether the fence language tag denotes a plaintext block (empty, ``text``, or ``plaintext``).
 */
export function isPlainTextFenceLanguage(rawLang: string): boolean {
  const trimmed = rawLang.trim()
  if (!trimmed) return true
  const normalized = normalizePrismLanguage(trimmed)
  return normalized === 'plaintext' || normalized === 'text'
}

/**
 * Whether plaintext fence body contains math delimiters worth rendering.
 */
export function plainTextCodeContainsMath(code: string): boolean {
  if (!code) return false
  if (INLINE_MATH_IN_LINE_RE.test(code)) return true
  if (/\$\$[\s\S]+?\$\$/.test(code)) return true
  if (/\\\(|\\\[/.test(code)) return true
  return false
}

/**
 * Whether a fenced code block should use math-aware plaintext rendering instead of Prism.
 */
export function shouldRenderPlainTextMathBlock(rawLang: string, code: string): boolean {
  return isPlainTextFenceLanguage(rawLang) && plainTextCodeContainsMath(code)
}

/**
 * Escape HTML metacharacters for fallback text nodes.
 */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * Render one TeX fragment with KaTeX; fall back to escaped delimited source on failure or prose-like bodies.
 */
export function renderPlainTextMathToHtml(tex: string, displayMode = false): string {
  const trimmed = tex.trim()
  if (!trimmed) return ''
  const body = repairMathBody(trimmed)
  if (isProseLikeMathBody(body)) {
    return escapeHtml(displayMode ? `$$${tex}$$` : `$${tex}$`)
  }
  try {
    return katex.renderToString(body, {
      output: 'html',
      strict: 'ignore',
      throwOnError: false,
      displayMode,
    })
  } catch {
    return escapeHtml(displayMode ? `$$${tex}$$` : `$${tex}$`)
  }
}

/**
 * Split one line of a plaintext code block into alternating text and math segments.
 */
export function splitLineIntoPlainTextMathSegments(line: string): PlainTextMathSegment[] {
  const segments: PlainTextMathSegment[] = []
  let i = 0
  const n = line.length

  while (i < n) {
    if (line[i] === '$' && i + 1 < n && line[i + 1] === '$') {
      const close = line.indexOf('$$', i + 2)
      if (close < 0) {
        segments.push({ type: 'text', value: line.slice(i) })
        break
      }
      const body = line.slice(i + 2, close)
      segments.push({ type: 'display', value: body })
      i = close + 2
      continue
    }

    const open = indexOfUnescapedDollar(line, i)
    if (open < 0) {
      segments.push({ type: 'text', value: line.slice(i) })
      break
    }

    if (open > i) {
      segments.push({ type: 'text', value: line.slice(i, open) })
    }

    const close = indexOfUnescapedDollar(line, open + 1)
    if (close < 0) {
      segments.push({ type: 'text', value: line.slice(open) })
      break
    }

    segments.push({ type: 'inline', value: line.slice(open + 1, close) })
    i = close + 1
  }

  if (segments.length === 0) {
    segments.push({ type: 'text', value: line })
  }

  return segments
}
