# Plain-Text Code Block Math Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render KaTeX inside plaintext fenced code blocks in agent chat while preserving block chrome and existing markdown math.

**Architecture:** Intercept plaintext fences in `createPreBlock`, route to `PlainTextMathCodeBlock` that splits lines into text/math segments and calls `katex.renderToString`. Optionally preprocess math inside plaintext fences before remark parse.

**Tech Stack:** React, KaTeX, existing `normalizeMarkdownMath` helpers

**Spec:** `docs/superpowers/specs/2026-07-01-plain-text-codeblock-math-design.md`

---

### Task 1: Pure helpers (`plainTextMathBlock.ts`)

**Files:**
- Create: `frontend/src/components/markdown/plainTextMathBlock.ts`

- [ ] Add `isPlainTextFenceLanguage`, `plainTextCodeContainsMath`, `shouldRenderPlainTextMathBlock`
- [ ] Add `splitLineIntoPlainTextMathSegments` + `renderPlainTextMathToHtml` using `repairMathBody` / `isProseLikeMathBody`

### Task 2: React component

**Files:**
- Create: `frontend/src/components/markdown/PlainTextMathCodeBlock.tsx`

- [ ] Mirror `PrismCodeWithCopy` header/copy; body renders line segments

### Task 3: Wire MinervaMarkdown + CSS

**Files:**
- Modify: `frontend/src/components/markdown/MinervaMarkdown.tsx`
- Modify: `frontend/src/components/markdown/MinervaMarkdown.css`

### Task 4: Preprocess plaintext fence bodies

**Files:**
- Modify: `frontend/src/components/markdown/normalizeMarkdownMath.ts`

- [ ] Add `mapInsidePlainTextFencedCodeBlocks`; call from `normalizeMarkdownForAgent`

### Task 5: Verify

- [ ] Run `npm run build:test` in `frontend`
