import { describe, expect, it } from 'vitest'
import { unified } from 'unified'
import remarkParse from 'remark-parse'
import { visit } from 'unist-util-visit'
import { MINERVA_MARKDOWN_REMARK_PLUGINS } from '@/components/markdown/markdownPlugins'
import {
  balanceExtraClosingBraces,
  convertLatexBracketMathDelimiters,
  isProseLikeMathBody,
  normalizeMarkdownForAgent,
  wrapBareLatexTextCommands,
  repairMissingInlineMathClosers,
  unwrapInlineMathFromBoldSpans,
  wrapBareTexInParentheses,
  wrapCjkInMathBody,
} from '@/components/markdown/normalizeMarkdownMath'

const USER_EULER_LIST_SNIPPET = `- **特殊值（\\(\\theta = \\pi\\)）**：得到 **欧拉恒等式**  
  \\[
  e^{i\\pi} + 1 = 0
  \\]  
  被誉为“数学中最美的公式”，因为它将 **自然常数 \\(e\\)、虚数单位 \\(i\\)、圆周率 \\(\\pi\\)、加法单位元 \\(0\\) 和乘法单位元 \\(1\\)** 统一在一个等式中。
- **几何意义**：在复平面上，\\(e^{i\\theta}\\) 表示单位圆上角度为 \\(\\theta\\) 的点，其模长为 1。

---

### **2. 多面体欧拉公式（拓扑学）**
\\[
V - E + F = 2
\\]
**解释**：
- **含义**：描述凸多面体的顶点数 \\(V\\)、边数 \\(E\\) 和面数 \\(F\\) 之间的关系。
- **例子**：立方体的 \\(V=8, E=12, F=6\\)，满足 \\(8-12+6=2\\)。
- **推广**：对任意与球面同胚的连通平面图，该公式成立（此时 \\(V-E+F=1\\) 需根据连通性调整）。`

const EULER_FORMULAS_MARKDOWN = `### **1. 复分析中的欧拉公式（最著名）**
\\[
e^{i\\theta} = \\cos\\theta + i\\sin\\theta
\\]
**解释**：
- **含义**：将复数指数函数与三角函数联系起来，建立了实数域与复数域的桥梁。
- **特殊值（\\(\\theta = \\pi\\)）**：得到 **欧拉恒等式**  
  \\[
  e^{i\\pi} + 1 = 0
  \\]  
  被誉为“数学中最美的公式”，因为它将 **自然常数 \\(e\\)、虚数单位 \\(i\\)、圆周率 \\(\\pi\\)、加法单位元 \\(0\\) 和乘法单位元 \\(1\\)** 统一在一个等式中。
- **几何意义**：在复平面上，\\(e^{i\\theta}\\) 表示单位圆上角度为 \\(\\theta\\) 的点，其模长为 1。

---

### **2. 多面体欧拉公式（拓扑学）**
\\[
V - E + F = 2
\\]
**解释**：
- **含义**：描述凸多面体的顶点数 \\(V\\)、边数 \\(E\\) 和面数 \\(F\\) 之间的关系。
- **例子**：立方体的 \\(V=8, E=12, F=6\\)，满足 \\(8-12+6=2\\)。
- **推广**：对任意与球面同胚的连通平面图，该公式成立（此时 \\(V-E+F=1\\) 需根据连通性调整）。`

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

describe('unwrapInlineMathFromBoldSpans', () => {
  it('pulls $...$ out of ** so remark-math can parse', () => {
    expect(unwrapInlineMathFromBoldSpans('**自然常数 $e$、虚数单位 $i$**')).toBe(
      '**自然常数 **$e$**、虚数单位 **$i$',
    )
  })

  it('keeps bold-only spans unchanged', () => {
    expect(unwrapInlineMathFromBoldSpans('**欧拉恒等式**')).toBe('**欧拉恒等式**')
  })

  it('unwraps bare **F(\\omega)** to inline math', () => {
    expect(unwrapInlineMathFromBoldSpans('**F(\\omega)**')).toBe('$F(\\omega)$')
  })

  it('unwraps \\( ... \\) inside bold after bracket conversion', () => {
    expect(unwrapInlineMathFromBoldSpans('**\\( F(\\omega) \\)**')).toBe('$F(\\omega)$')
  })
})

const FOURIER_CONTINUOUS_FREQ_LINE =
  '变成连续的频率 \\( \\omega \\，离散的系数 \\( c_n \\) 变成连续的频谱密度函数'

const FOURIER_FULL_SENTENCE =
  '从级数形式出发，当 $T \\to \\infty$ 时，离散的频率 $n\\omega_0$ 变成连续的频率 \\( \\omega \\，\\text{离散的系数} \\( c_n \\) 变成连续的频谱密度函数 $F(\\omega)$。'

const FOURIER_TRANSFORM_PAIR_LINE =
  '令方括号内的部分为 \\( F(\\omega) \\)，就得到了傅里叶变换对。'

const FOURIER_CORE_PARAGRAPH =
  '**核心**：傅里叶变换 \\( F(\\omega) \\) 描述了信号 \\( f(t) \\) 在各个连续频率 \\( \\omega \\) 上的“密度”或“强度”。'

const FOURIER_BOLD_FORMULA_LINE =
  '6. 令方括号内的部分为 **F(\\omega)**，就得到了傅里叶变换对。'

describe('wrapBareLatexTextCommands', () => {
  it('wraps bare \\text{} outside math delimiters', () => {
    expect(wrapBareLatexTextCommands(String.raw`\text{离散的系数}`)).toBe(
      String.raw`$\text{离散的系数}$`,
    )
    expect(wrapBareLatexTextCommands(String.raw`$\text{ok}$`)).toBe(String.raw`$\text{ok}$`)
  })
})

describe('convertLatexBracketMathDelimiters', () => {
  it('splits \\( \\omega \\， prose \\( c_n \\) into separate inline math spans', () => {
    const out = convertLatexBracketMathDelimiters(FOURIER_CONTINUOUS_FREQ_LINE)
    expect(out).toBe('变成连续的频率 $\\omega$，离散的系数 $c_n$ 变成连续的频谱密度函数')
    expect(out).not.toContain('\\(')
    expect(out).not.toContain('\\omega \\')
  })

  it('handles nested \\( before second variable', () => {
    const out = convertLatexBracketMathDelimiters(
      String.raw`\( \omega \,\text{离散的系数} \( c_n \)`,
    )
    expect(out).toBe(String.raw`$\omega \,\text{离散的系数}$$c_n$`)
  })

  it('keeps \\, thin space before \\text inside one math fragment', () => {
    const out = convertLatexBracketMathDelimiters(
      String.raw`\( \omega \，\text{离散的系数} \( c_n \)`,
    )
    expect(out).toBe(String.raw`$\omega \,\text{离散的系数}$$c_n$`)
  })

  it('converts \\[...\\] to flow $$ fences', () => {
    const input = String.raw`\[
e^{i\theta} = \cos\theta + i\sin\theta
\]`
    expect(convertLatexBracketMathDelimiters(input)).toBe(
      String.raw`$$
e^{i\theta} = \cos\theta + i\sin\theta
$$`,
    )
  })

  it('converts \\(...\\) to inline $ fences', () => {
    expect(convertLatexBracketMathDelimiters(String.raw`\(\theta = \pi\)`)).toBe(
      String.raw`$\theta = \pi$`,
    )
  })

  it('leaves fenced code blocks unchanged via normalizeMarkdownForAgent', () => {
    const input = '```\n\\[x\\]\n```\n\\(y\\)'
    expect(normalizeMarkdownForAgent(input)).toBe('```\n\\[x\\]\n```\n$y$')
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

  it('converts LaTeX bracket delimiters in Euler formula sample', () => {
    const out = normalizeMarkdownForAgent(EULER_FORMULAS_MARKDOWN)
    expect(out).not.toContain('\\[')
    expect(out).not.toContain('\\]')
    expect(out).not.toMatch(/\\\([^)]*\\\)/)
    expect(out).toContain(String.raw`e^{i\theta} = \cos\theta + i\sin\theta`)
    expect(out).toContain(String.raw`$\theta = \pi$`)
    expect(out).toContain('V - E + F = 2')
    expect(out).toContain(String.raw`$V=8, E=12, F=6$`)
    expect(out.match(/\$\$/g)?.length).toBeGreaterThanOrEqual(6)
  })

  it('parses Euler formula sample into flow and inline math nodes', () => {
    const md = normalizeMarkdownForAgent(EULER_FORMULAS_MARKDOWN)
    const processor = unified().use(remarkParse).use(MINERVA_MARKDOWN_REMARK_PLUGINS)
    const mdast = processor.runSync(processor.parse(md))
    let flowMath = 0
    let inlineMath = 0
    visit(mdast, 'math', () => {
      flowMath++
    })
    visit(mdast, 'inlineMath', () => {
      inlineMath++
    })
    expect(flowMath).toBeGreaterThanOrEqual(3)
    expect(inlineMath).toBeGreaterThanOrEqual(1)
  })

  it('parses inline math outside bold after bracket conversion', () => {
    const md = normalizeMarkdownForAgent(
      '- **几何意义**：在复平面上，\\(e^{i\\theta}\\) 表示单位圆上角度为 \\(\\theta\\) 的点。',
    )
    const processor = unified().use(remarkParse).use(MINERVA_MARKDOWN_REMARK_PLUGINS)
    const mdast = processor.runSync(processor.parse(md))
    let inlineMath = 0
    visit(mdast, 'inlineMath', () => {
      inlineMath++
    })
    expect(inlineMath).toBeGreaterThanOrEqual(2)
  })

  it('dedents 2-space list display math and parses flow + inline in user snippet', () => {
    const md = normalizeMarkdownForAgent(USER_EULER_LIST_SNIPPET)
    expect(md).toMatch(/^\$\$/m)
    expect(md).not.toMatch(/^\s{2}\$\$/m)
    const processor = unified().use(remarkParse).use(MINERVA_MARKDOWN_REMARK_PLUGINS)
    const mdast = processor.runSync(processor.parse(md))
    let flowMath = 0
    let inlineMath = 0
    visit(mdast, 'math', () => {
      flowMath++
    })
    visit(mdast, 'inlineMath', () => {
      inlineMath++
    })
    expect(flowMath).toBeGreaterThanOrEqual(2)
    expect(inlineMath).toBeGreaterThanOrEqual(6)
  })

  it('unwraps bold around constants in Euler identity prose', () => {
    const md = normalizeMarkdownForAgent(USER_EULER_LIST_SNIPPET)
    expect(md).toContain('**自然常数 **$e$**')
    expect(md).toContain('虚数单位 **$i$**')
    expect(md).not.toContain('**自然常数 $e$')
  })

  it('renders Fourier transform pair and core paragraph inline math', () => {
    const out = normalizeMarkdownForAgent(
      `${FOURIER_TRANSFORM_PAIR_LINE}\n\n${FOURIER_CORE_PARAGRAPH}`,
    )
    expect(out).toContain('$F(\\omega)$')
    expect(out).toContain('$f(t)$')
    expect(out).not.toContain('\\(')
    expect(out).not.toContain('**F(\\omega)**')
    const processor = unified().use(remarkParse).use(MINERVA_MARKDOWN_REMARK_PLUGINS)
    const mdast = processor.runSync(processor.parse(out))
    let inlineMath = 0
    visit(mdast, 'inlineMath', () => {
      inlineMath++
    })
    expect(inlineMath).toBeGreaterThanOrEqual(4)
  })

  it('renders **F(\\omega)** in bold as KaTeX', () => {
    const out = normalizeMarkdownForAgent(FOURIER_BOLD_FORMULA_LINE)
    expect(out).toContain('$F(\\omega)$')
    expect(out).not.toContain('**F(\\omega)**')
  })

  it('renders Fourier continuous-frequency sentence without literal LaTeX in prose', () => {
    const out = normalizeMarkdownForAgent(FOURIER_FULL_SENTENCE)
    expect(out).toContain(String.raw`$\omega \,\text{离散的系数}$`)
    expect(out).toContain('$c_n$')
    expect(out).not.toMatch(/\\omega \\，/)
    expect(out).not.toContain('\\(')
    const processor = unified().use(remarkParse).use(MINERVA_MARKDOWN_REMARK_PLUGINS)
    const mdast = processor.runSync(processor.parse(out))
    let inlineMath = 0
    visit(mdast, 'inlineMath', () => {
      inlineMath++
    })
    expect(inlineMath).toBeGreaterThanOrEqual(4)
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
