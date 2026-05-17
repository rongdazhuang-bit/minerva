import { normalizeLooseInlineMathDelimiters } from '@/features/file-ocr/applyOcrMarkdownImagePlaceholders'

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
 *
 * Skips content already inside ``\\text{...}``.
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
 * Preprocess agent chat Markdown so ``remark-math`` + KaTeX render model TeX reliably.
 */
export function normalizeAgentChatMath(markdown: string): string {
  return mapOutsideFencedCodeBlocks(markdown, (chunk) =>
    normalizeInlineMathSpans(
      wrapBareTexInParentheses(normalizeLooseInlineMathDelimiters(chunk)),
    ),
  )
}
