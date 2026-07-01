# 纯文本代码块内 LaTeX 公式渲染设计

**日期**：2026-07-01  
**状态**：待实现  
**范围**：Agent 对话 Markdown 渲染中，当模型将带 `$...$` 的说明文字误包进「纯文本」围栏代码块时，在保留代码块 UI（标题栏 + 复制）的前提下块内渲染 KaTeX 公式；不得破坏块外及表格等既有公式渲染。

**关联代码**：

- `frontend/src/components/markdown/MinervaMarkdown.tsx`（围栏拦截、Prism/Mermaid/Chart 分支）
- `frontend/src/components/markdown/normalizeMarkdownMath.ts`（`mapOutsideFencedCodeBlocks` 跳过围栏内数学预处理）
- `frontend/src/components/markdown/remarkMathInTableCells.ts`（表格单元格内公式重解析，可借鉴模式）

---

## 1. 问题描述

### 1.1 现象

模型输出类似：

````markdown
$$
P = \frac{1}{2} \rho A v^3 C_p
$$

```text
其中：
- $\rho$：空气密度 ($\mathrm{kg/m^{3}}$)。
- $A$：扫风面积 ($\mathrm{m^{2}}$)，计算公式为 $A = \pi \cdot \left(\frac{D}{2}\right)^2$。
```
````

块外 `$$...$$` 正常渲染；围栏内 `$...$` 显示为原始字符（Prism 纯文本高亮）。

### 1.2 根因

1. `normalizeMarkdownForAgent` 通过 `mapOutsideFencedCodeBlocks` **刻意不对围栏内**做数学预处理。
2. Agent preset 下所有围栏（除 mermaid/chart）走 `PrismCodeWithCopy`，无 remark-math / KaTeX 路径。
3. 表格单元格已有 `remarkMathInTableCells` 补救，代码块无对应逻辑。

### 1.3 需求决策摘要（brainstorming 定稿）

| 项 | 决策 |
|----|------|
| 作用范围 | **仅**纯文本类围栏：无语言标签、`text`、`plaintext` |
| 呈现方式 | **保留**代码块外观（「纯文本」标签 + 复制按钮），块内逐行渲染公式 |
| 编程语言围栏 | **不处理**（python、bash 等仍走 Prism；bash `$VAR` 不受影响） |
| OCR preset | **本期不在范围** |
| 预处理 | 可选：对纯文本围栏内运行轻量数学规范化（定界符转换、body 修复） |

---

## 2. 目标与成功标准

### 2.1 目标

- 纯文本围栏内 `$...$`、`$$...$$`、`\(...\)`、`\[...\]` 经 KaTeX 渲染为数学符号。
- 复制按钮仍复制**原始源码**（含 `$` 定界符）。
- 块外段落/块级公式、GFM 表格单元格公式、Mermaid/Chart 围栏行为与改前一致。

### 2.2 成功标准

- 截图场景（纯文本围栏 + 中文说明 + 行内 `$...$`）公式正确显示。
- 无 `$` 的纯文本围栏仍走 Prism（或等价纯文本展示），无回归。
- ` ```bash ` 等含 `$` 的代码块不触发公式渲染。
- KaTeX 报错时回退显示原始 `$...$` 文本，不白屏。

### 2.3 非目标

- 不把纯文本围栏「去围栏」还原为 GFM 列表/段落（用户明确保留代码块 UI）。
- 不在所有语言围栏内渲染公式。
- 不处理 OCR preset（后续可按同样模式扩展）。

---

## 3. 方案选型

### 3.1 候选方案

| 方案 | 说明 | 结论 |
|------|------|------|
| A. 专用 `PlainTextMathCodeBlock` | 拦截纯文本围栏，行内 KaTeX 注入 | **采用** |
| B. 块内嵌套 Mini ReactMarkdown | 子树再走 remark-math | 列表样式好但误解析风险高 |
| C. 预处理去围栏 | 去掉 ``` 还原为 Markdown | 用户拒绝 |

### 3.2 架构概览

```text
ReactMarkdown → pre (AGENT_PRE_BLOCK)
                  └─ code.language-*
                       ├─ mermaid      → MermaidBlock
                       ├─ chart        → MarkdownChartBlock
                       ├─ plaintext/text/无标签 + 含公式 → PlainTextMathCodeBlock  [新增]
                       └─ 其他         → PrismCodeWithCopy
```

---

## 4. 组件设计

### 4.1 触发条件 `shouldRenderPlainTextMathBlock(rawLang, code)`

同时满足：

1. **语言**：`normalizePrismLanguage(rawLang)` 为 `plaintext` 或 `text`，或 `rawLang` 为空。
2. **内容**：含 `$...$`、`$$...$$`，或 `\(` / `\[` 定界符（与 `containsBareLatex` 互补，优先 `$` 检测）。

不满足任一则继续走 `PrismCodeWithCopy`。

### 4.2 `PlainTextMathCodeBlock`

**文件**：`frontend/src/components/markdown/PlainTextMathCodeBlock.tsx`（新建，保持 `MinervaMarkdown.tsx` 体量）

**结构**（对齐 `PrismCodeWithCopy`）：

```text
minerva-md-syntax-host
├── minerva-md-syntax-header（语言标签 + 复制按钮）
└── minerva-md-plain-math-body
    └── 按 \n 分行，每行 PlainTextMathLine
```

**`PlainTextMathLine`**：

- 将一行文本按 `$...$` / `$$...$$` 拆分（复用与 `rehypeMathInHtmlTableCells` 类似的定界符扫描，支持 `indexOfUnescapedDollar` 避免转义 `$` 误判）。
- 数学片段：调用 `katex.renderToString`，选项与全局一致：`{ output: 'html', strict: 'ignore', throwOnError: false }`。
- 渲染前对 body 调用 `repairMathBody`；若 `isProseLikeMathBody` 为 true 则**不**当公式渲染。
- 失败：保留原始 `$...$` 文本节点。

**复制**：与 `PrismCodeWithCopy` 相同，复制完整 `code`  prop（原始 markdown 围栏内容）。

**样式**（`MinervaMarkdown.css`）：

- `.minerva-md-plain-math-body`：等宽字号、行距与 `.minerva-md-syntax` 接近；`white-space: pre-wrap`。
- 块内 `.katex` 字号与行内 math 一致，垂直对齐 baseline。

### 4.3 与 `MinervaMarkdown.tsx` 集成

在 `createPreBlock` 的 Prism 分支前：

```typescript
if (shouldRenderPlainTextMathBlock(rawLang, inner)) {
  return <PlainTextMathCodeBlock code={inner} rawLanguage={rawLang} />
}
```

仅 Agent preset（`richCode === true`）启用。

---

## 5. 预处理（可选增强）

### 5.1 `mapInsidePlainTextFencedCodeBlocks`

**文件**：`normalizeMarkdownMath.ts`

对匹配纯文本围栏（语言为空 / text / plaintext）的围栏**内部正文**依次应用：

1. `convertLatexBracketMathDelimiters`（`\(...\)` → `$...$`）
2. `normalizeInlineMathSpans`（body 修复、CJK `\text{}` 等）

**不**改变 `mapOutsideFencedCodeBlocks` 对外层 chunk 的现有管线；仅在围栏 split 后对符合条件的 fence body 做 in-place 替换。

围栏识别正则需与 `mapOutsideFencedCodeBlocks` 一致，并解析 opening fence 的 info string 判断语言。

在 `normalizeMarkdownForAgent` 最外层、进入 `mapOutsideFencedCodeBlocks` **之前**调用一次即可。

---

## 6. 回归约束

| 场景 | 期望 |
|------|------|
| 普通段落 `$x$`、块级 `$$` | 不变 |
| GFM 表格单元格公式 | 不变 |
| ` ```python ` 等代码块 | 不变 |
| ` ```bash ` 含 `$HOME` | 不变，不走 PlainTextMath |
| ` ```mermaid ` / chart | 不变 |
| 纯文本围栏无 `$` | 仍 Prism |
| Agent 块外 + 块内公式同页 | 均正常 |

---

## 7. 测试计划

### 7.1 单元测试（Vitest）

**文件**：`frontend/src/components/markdown/plainTextMathCodeBlock.test.ts`（或同级）

| 用例 | 断言 |
|------|------|
| `shouldRenderPlainTextMathBlock('', '- $\\rho$：…')` | true |
| `shouldRenderPlainTextMathBlock('bash', 'echo $HOME')` | false |
| `shouldRenderPlainTextMathBlock('python', 'x = 1')` | false |
| 行内拆分 + KaTeX | `$\\rho$` → 含 `.katex` HTML 或等价 |
| `isProseLikeMathBody` 误判 | 长中文 `$...$` 不渲染为 math |
| KaTeX 非法输入 | 回退原始 `$...$` |

### 7.2 手动验证

- Agent 对话复现截图场景。
- 同消息含块外 `$$` 与块内 `$`。
- 复制纯文本块内容，粘贴仍为原始 `$` 源码。

---

## 8. 文件变更清单

| 文件 | 动作 |
|------|------|
| `frontend/src/components/markdown/PlainTextMathCodeBlock.tsx` | 新建 |
| `frontend/src/components/markdown/plainTextMathBlock.ts` | 新建：触发条件、行内拆分、KaTeX 渲染纯函数 |
| `frontend/src/components/markdown/MinervaMarkdown.tsx` | 拦截分支 |
| `frontend/src/components/markdown/MinervaMarkdown.css` | 块内样式 |
| `frontend/src/components/markdown/normalizeMarkdownMath.ts` | 可选：`mapInsidePlainTextFencedCodeBlocks` |
| `frontend/src/components/markdown/index.ts` | 导出（若需对外测试） |

---

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 纯文本块内 `$` 非公式（货币等） | 仅 `$...$` 成对匹配；`isProseLikeMathBody` 过滤 |
| 与 Prism 样式不一致 | 复用 `minerva-md-syntax-host` 外壳 |
| 预处理误改围栏边界 | 仅匹配 text/plain/空语言；单元测试覆盖 bash |

---

## 10. 后续扩展（非本期）

- OCR preset 同样拦截纯文本围栏。
- 纯文本块内裸 TeX（无 `$`）via `wrapBareLatexSpansInPlainText`（用户未要求，YAGNI）。
