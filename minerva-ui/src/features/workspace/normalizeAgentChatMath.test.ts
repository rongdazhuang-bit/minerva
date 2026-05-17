import { describe, expect, it } from 'vitest'
import {
  balanceExtraClosingBraces,
  normalizeAgentChatMath,
  wrapBareTexInParentheses,
  wrapCjkInMathBody,
} from '@/features/workspace/normalizeAgentChatMath'

describe('balanceExtraClosingBraces', () => {
  it('removes one stray closing brace before end of math', () => {
    expect(balanceExtraClosingBraces(String.raw`\vec{F}_{人\to箱}}`)).toBe(
      String.raw`\vec{F}_{人\to箱}`,
    )
  })
})

describe('wrapCjkInMathBody', () => {
  it('wraps CJK in text command for KaTeX', () => {
    expect(wrapCjkInMathBody(String.raw`_{人\to箱}`)).toBe(
      String.raw`_{\text{人}\to\text{箱}}`,
    )
  })

  it('does not double-wrap existing text command', () => {
    expect(wrapCjkInMathBody(String.raw`\text{人}`)).toBe(String.raw`\text{人}`)
  })
})

describe('wrapBareTexInParentheses', () => {
  it('adds dollar fences around parenthesized TeX', () => {
    expect(wrapBareTexInParentheses('人推箱子 (\\vec{F}_{人\\to箱}}) 上')).toContain(
      '($\\vec{F}_{\\text{人}\\to\\text{箱}}$)',
    )
  })

  it('handles fullwidth parentheses', () => {
    expect(wrapBareTexInParentheses('（\\vec{F}_{箱\\to人}}）')).toContain(
      '（$\\vec{F}_{\\text{箱}\\to\\text{人}}$）',
    )
  })
})

describe('normalizeAgentChatMath', () => {
  it('fixes inline math with extra brace and CJK subscripts', () => {
    const input = '人推箱子（$\\vec{F}_{人\\to箱}}$）作用在箱子上。'
    const out = normalizeAgentChatMath(input)
    expect(out).toBe('人推箱子（$\\vec{F}_{\\text{人}\\to\\text{箱}}$）作用在箱子上。')
    expect(out).not.toMatch(/\\to\\text\{箱\}\}\}/)
  })

  it('leaves fenced code blocks unchanged', () => {
    const input = '```\n(\\vec{x})\n```\n(\\vec{y})\n'
    expect(normalizeAgentChatMath(input)).toBe(
      '```\n(\\vec{x})\n```\n($\\vec{y}$)\n',
    )
  })
})
