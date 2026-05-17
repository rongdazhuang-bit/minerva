import { describe, expect, it } from 'vitest'
import {
  balanceExtraClosingBraces,
  isProseLikeMathBody,
  normalizeMarkdownForAgent,
  repairMissingInlineMathClosers,
  wrapBareTexInParentheses,
  wrapCjkInMathBody,
} from '@/components/markdown/normalizeMarkdownMath'

describe('repairMissingInlineMathClosers', () => {
  it('closes inline math before CJK comma when model omits trailing $', () => {
    const input =
      '通常令旋转因子 $W_N = e^{-i \\frac{2\\pi}{N}}，则公式简化为 $X[k] = \\sum_{n=0}^{N-1} x[n] W_N^{kn}$。'
    const out = repairMissingInlineMathClosers(input)
    expect(out).toContain(String.raw`\frac{2\pi}{N}}$，则公式简化为`)
    expect(out).not.toContain(String.raw`\frac{2\pi}{N}}，则`)
  })
})

describe('isProseLikeMathBody', () => {
  it('detects model-wrapped Chinese sentences', () => {
    expect(isProseLikeMathBody('DFT 的推导可以看作是对连续傅里叶变换（FT）进行离散化')).toBe(true)
    expect(isProseLikeMathBody('3.2 推导思路（连续信号的采样与截断）')).toBe(true)
  })

  it('keeps real formulas', () => {
    expect(isProseLikeMathBody(String.raw`\omega_0 = \frac{2\pi}{NT}`)).toBe(false)
    expect(isProseLikeMathBody('f(t)')).toBe(false)
    expect(isProseLikeMathBody(String.raw`dt \to T`)).toBe(false)
    expect(isProseLikeMathBody('x[n] = f(nT)')).toBe(false)
  })
})

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

describe('normalizeMarkdownForAgent', () => {
  it('fixes inline math with extra brace and CJK subscripts', () => {
    const input = '人推箱子（$\\vec{F}_{人\\to箱}}$）作用在箱子上。'
    const out = normalizeMarkdownForAgent(input)
    expect(out).toBe('人推箱子（$\\vec{F}_{\\text{人}\\to\\text{箱}}$）作用在箱子上。')
    expect(out).not.toMatch(/\\to\\text\{箱\}\}\}/)
  })

  it('leaves fenced code blocks unchanged', () => {
    const input = '```\n(\\vec{x})\n```\n(\\vec{y})\n'
    expect(normalizeMarkdownForAgent(input)).toBe(
      '```\n(\\vec{x})\n```\n($\\vec{y}$)\n',
    )
  })

  it('rewrites ν unit derivation (multi \\frac + \\text{}) as flow display math', () => {
    const input = String.raw`推导 $\nu$ 的单位：
$$ \frac{\text{N} \cdot \text{s} / \text{m}^2}{\text{kg} / \text{m}^3} = \frac{(\text{kg} \cdot \text{m} / \text{s}^2) \cdot \text{s} / \text{m}^2}{\text{kg} / \text{m}^3} = \frac{\text{m}^2}{\text{s}} $$`
    const out = normalizeMarkdownForAgent(input)
    expect(out).toContain(String.raw`推导 $\nu$ 的单位：`)
    expect(out).not.toMatch(/\(\$\\text\{kg\}/)
    expect(out).toContain(String.raw`(\text{kg} \cdot \text{m} / \text{s}^2)`)
    expect(out).toMatch(/\n\n\$\$\n\\frac\{\\text\{N\}/)
    expect(out).toMatch(
      /\\frac\{\\text\{N\} \\cdot \\text\{s\} \/ \\text\{m\}\^2\}\{\\text\{kg\} \/ \\text\{m\}\^3\}[\s\S]+\\frac\{\\text\{m\}\^2\}\{\\text\{s\}\}\n\$\$/,
    )
  })

  it('keeps short single-line $$ as inline-style fences', () => {
    const input = '令 $$E=mc^2$$ 与 $$x^2$$ 成立。'
    expect(normalizeMarkdownForAgent(input)).toBe(input)
  })

  it('keeps single \\frac with \\text{} as inline-style $$', () => {
    const input = String.raw`密度 $$\frac{\text{kg}}{\text{m}^3}$$ 已知。`
    expect(normalizeMarkdownForAgent(input)).toBe(input)
  })

  it('keeps two-fraction equality without enough \\text{} units as inline $$', () => {
    const input = String.raw`$$ \frac{a}{b} = \frac{c}{d} $$`
    expect(normalizeMarkdownForAgent(input)).toBe(input)
  })

  it('does not alter multiline display math bodies', () => {
    const input = String.raw`$$
\begin{align}
a &= b \\
c &= d
\end{align}
$$`
    expect(normalizeMarkdownForAgent(input)).toBe(input)
  })

  it('dedents $$ under list items and promotes γ unit line to flow display', () => {
    const input = `*   **水的重度**：\n    $$ \\gamma = 1000 \\times 9.81 = 9810 \\, \\text{N/m}^3 = 9.81 \\, \\text{kN/m}^3 $$`
    const out = normalizeMarkdownForAgent(input)
    expect(out).toContain('$$\n\\gamma = 1000')
    expect(out).not.toMatch(/^\s{4,}\$\$/m)
  })

  it('promotes p = \\gamma h style display equations', () => {
    const input = '$$ p = \\gamma h $$'
    const out = normalizeMarkdownForAgent(input)
    expect(out).toBe('$$\np = \\gamma h\n$$')
  })

  it('keeps compact E=mc^2 as inline $$', () => {
    expect(normalizeMarkdownForAgent('$$E=mc^2$$')).toBe('$$E=mc^2$$')
  })

  it('does not wrap CJK in \\text{} inside GFM table rows during preprocess', () => {
    const input = `| 类型 | 公式 |
| :--- | :--- |
| 连续、周期 | $\\int f(t) dt$ |`
    const out = normalizeMarkdownForAgent(input)
    expect(out).toContain('连续、周期')
    expect(out).not.toMatch(/\\text\{连续\}/)
    expect(out).toContain('$\\int f(t) dt$')
  })

  it('keeps Fourier summary table markdown intact (math parsed by remarkMathInTableCells)', () => {
    const input = `| 变换类型 | 核心公式 |
| :--- | :--- |
| **DFT** | $\\sum_{n=0}^{N-1} x[n] e^{-i \\frac{2\\pi}{N} kn}$ |`
    const out = normalizeMarkdownForAgent(input)
    expect(out).toContain('**DFT**')
    expect(out).toContain('$\\sum_{n=0}^{N-1}')
    expect(out).not.toContain('math-inline')
  })

  it('dedents indented list notes and sub-bullets (not GFM code blocks)', () => {
    const input = `*   **密度**
    $$ \\rho = \\frac{m}{V} $$
    *(水的密度通常取 $1000 \\, \\text{kg/m}^3$)*
*   **静水压强**
    *   $p_0$: 液面压强 (通常为大气压)
    *   $h$: 距液面的垂直深度`
    const out = normalizeMarkdownForAgent(input)
    expect(out).toContain('*(水的密度通常取 $1000')
    expect(out).not.toMatch(/^\s{4}\*\(/m)
    expect(out).toContain('*   $p_0$: 液面压强')
    expect(out).not.toMatch(/^\s{4}\*\s+\$p_0/m)
  })
})
