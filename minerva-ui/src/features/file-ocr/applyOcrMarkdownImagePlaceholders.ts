/**
 * Replace OCR engine placeholder substrings in markdown using a ``placeholder -> url`` map.
 *
 * Keys are applied in **descending length** order so shorter keys do not break longer ones.
 */
export function applyOcrMarkdownImagePlaceholders(
  text: string | null | undefined,
  images: Record<string, string> | null | undefined,
): string {
  const base = text ?? ''
  if (images == null || Object.keys(images).length === 0) {
    return base
  }
  const keys = Object.keys(images).sort((a, b) => b.length - a.length)
  let out = base
  for (const k of keys) {
    const val = images[k]
    if (val === undefined) continue
    out = out.split(k).join(val)
  }
  return out
}

/**
 * Tighten inline math dollar delimiters so ``remark-math`` recognizes OCR output like ``$ 7 , mm $``.
 *
 * Skips whitespace only immediately after an **opening** single ``$`` (not ``$$`` block math).
 */
export function normalizeLooseInlineMathDelimiters(text: string): string {
  let out = ''
  let i = 0
  let inSingleDollarMath = false

  while (i < text.length) {
    if (text[i] === '$' && text[i + 1] === '$') {
      const rest = text.indexOf('$$', i + 2)
      if (rest === -1) {
        out += text.slice(i)
        break
      }
      out += text.slice(i, rest + 2)
      i = rest + 2
      continue
    }

    if (text[i] === '$') {
      out += '$'
      i += 1
      if (!inSingleDollarMath) {
        inSingleDollarMath = true
        while (i < text.length && /\s/.test(text[i])) {
          i += 1
        }
      } else {
        inSingleDollarMath = false
      }
      continue
    }

    out += text[i]
    i += 1
  }

  return out
    .replace(/\(\s+\$(?!\$)/g, '($')
    .replace(/\[\s+\$(?!\$)/g, '[$')
    .replace(/（\s+\$(?!\$)/g, '（$')
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
 * Promote ``$...$`` pairs that contain ``\\tag`` / ``\\tag*`` to display math ``$$...$$``.
 *
 * KaTeX reliably renders equation tags in **display** mode; OCR often wraps tagged formulas in single dollars.
 * Pair delimiters are written without enforced newlines here; call ``normalizeDisplayMathFencesForRemarkMath``
 * afterward so ``remark-math`` parses block math as **flow** (``math-display``) rather than ``math-inline``.
 */
export function promoteInlineMathContainingTagToDisplay(text: string): string {
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
      const body = text.slice(bodyStart, close)
      if (/\\tag\*?/.test(body)) {
        const collapsed = body.replace(/\s{2,}/g, ' ')
        out += `$$${collapsed}$$`
      } else {
        out += text.slice(open, close + 1)
      }
      i = close + 1
      continue
    }

    out += text[i]
    i += 1
  }

  return out
}

/**
 * Rewrite every ``$$...$$`` span as ``$$\\n...\\n$$`` and trim / collapse interior whitespace.
 *
 * ``micromark-extension-math`` only treats **flow** math as display when the opening fence is followed by a
 * line ending; a single-line ``$$...$$`` is otherwise parsed as ``math-inline``, which breaks ``\\tag`` /
 * ``\\tag*`` under KaTeX.
 */
export function normalizeDisplayMathFencesForRemarkMath(text: string): string {
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
      const body = rawBody.replace(/\s{2,}/g, ' ').trim()
      out += `$$\n${body}\n$$`
      i = closeBlock + 2
      continue
    }

    out += text[i]
    i += 1
  }

  return out
}
