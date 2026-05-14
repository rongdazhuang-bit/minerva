import { describe, expect, it } from 'vitest'

import {
  applyOcrMarkdownImagePlaceholders,
  normalizeDisplayMathFencesForRemarkMath,
  normalizeLooseInlineMathDelimiters,
  promoteInlineMathContainingTagToDisplay,
} from './applyOcrMarkdownImagePlaceholders'

describe('normalizeLooseInlineMathDelimiters', () => {
  it('collapses whitespace after opening $ without touching $$', () => {
    const s = '外径为 $ 7 , mm $ ( $ 0.276 , in $)、阻抗 $ 50 , \\Omega $'
    expect(normalizeLooseInlineMathDelimiters(s)).toBe(
      '外径为 $7 , mm $ ($0.276 , in $)、阻抗 $50 , \\Omega $',
    )
  })

  it('does not alter consecutive dollar block markers', () => {
    expect(normalizeLooseInlineMathDelimiters('$$ x $$')).toBe('$$ x $$')
  })
})

describe('normalizeDisplayMathFencesForRemarkMath', () => {
  it('inserts newlines inside $$ fences so remark-math treats math as display flow', () => {
    expect(normalizeDisplayMathFencesForRemarkMath('$$ x $$')).toBe('$$\nx\n$$')
  })
})

describe('promoteInlineMathContainingTagToDisplay', () => {
  it('wraps inline math that uses \\tag* in display dollars for KaTeX', () => {
    const s =
      '准确度 $=\\frac{\\mid f_{1}-f_{0}\\mid}{f_{0}}\\times100\\% \\tag*{……(1)}$ 后文'
    const afterPromote = promoteInlineMathContainingTagToDisplay(s)
    expect(afterPromote).toBe(
      '准确度 $$=\\frac{\\mid f_{1}-f_{0}\\mid}{f_{0}}\\times100\\% \\tag*{……(1)}$$ 后文',
    )
    expect(normalizeDisplayMathFencesForRemarkMath(afterPromote)).toBe(
      '准确度 $$\n=\\frac{\\mid f_{1}-f_{0}\\mid}{f_{0}}\\times100\\% \\tag*{……(1)}\n$$ 后文',
    )
  })

  it('leaves ordinary inline math as single dollars', () => {
    expect(promoteInlineMathContainingTagToDisplay('令 $x=1$。')).toBe('令 $x=1$。')
  })

  it('passes through existing display blocks unchanged until fence normalizer runs', () => {
    const s = '$$a \\tag{1}$$ 与 $b$'
    expect(promoteInlineMathContainingTagToDisplay(s)).toBe(s)
    expect(normalizeDisplayMathFencesForRemarkMath(s)).toBe('$$\na \\tag{1}\n$$ 与 $b$')
  })

  it('trims spaces inside $$ display delimiters', () => {
    const s =
      '$$   工作频率准确度 =\\frac{\\mid f_{1}-f_{0}\\mid}{f_{0}}\\times100\\%   \\tag*{……(1)}$$;'
    expect(normalizeDisplayMathFencesForRemarkMath(promoteInlineMathContainingTagToDisplay(s))).toBe(
      '$$\n工作频率准确度 =\\frac{\\mid f_{1}-f_{0}\\mid}{f_{0}}\\times100\\% \\tag*{……(1)}\n$$;',
    )
  })
})

describe('applyOcrMarkdownImagePlaceholders', () => {
  it('returns empty string for null text and no images', () => {
    expect(applyOcrMarkdownImagePlaceholders(null, null)).toBe('')
  })

  it('applies longer keys before shorter keys', () => {
    const text = 'ab X ac'
    const images = { a: '1', ab: '2' }
    expect(applyOcrMarkdownImagePlaceholders(text, images)).toBe('2 X 1c')
  })

  it('leaves text unchanged when images map is empty', () => {
    expect(applyOcrMarkdownImagePlaceholders('hello', {})).toBe('hello')
  })
})
