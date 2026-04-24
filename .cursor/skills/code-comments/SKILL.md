---
name: code-comments
description: >-
  Defines when and how to write code comments in this repository (TypeScript/React
  frontend, Python backend). Use when adding or editing comments, documenting
  public APIs, reviewing comment quality, or when the user asks for comment
  standards、注释规范、或“给代码加注释”.
---

# 代码注释规范（Minerva）

## 目标

用**少量、高信噪比**的注释，帮助后续阅读者理解**意图、约束与副作用**；不把注释当成第二份实现说明。

## 语言

- **实现代码内**：注释、文档串以 **英文** 为主，与代码标识符语言一致。
- **业务/产品专名**（如多租户、工作空间）若只在中文需求里出现，可在注释中保留一次中英对照，避免歧义。

## 什么时候写

| 值得写 | 少写或省略 |
|--------|------------|
| 非显而易见的 **why**（为何这样实现、曾踩过哪些坑） | 重复标识符语义的 what（`i++` 递增 `i`） |
| **不变量/契约**（例如：必须先 `flush` 再建依赖行） | 对语言本身行为的说明 |
| **跨边界** 的公共导出（`export` 函数、包内 service） | 显而易见的单行 getter |
| **副作用**（写 localStorage、发全局事件、改 DOM class） | 与实现逐行同步的“翻译式”注释 |
| 魔法字符串/键的 **归一处说明**（若已集中在常量上，在常量处注释） | 每个调用点再抄一遍 |
| 复杂控制流/并发的前置 **Safety** 说明 | 整个文件逐函数头部模板化 `@returns` |

## TypeScript / React

- 对 **`export` 的函数/常量**：若行为非一目了然，用 **1～3 行**块注释或简短 JSDoc（`@param` 仅当类型不足以表达时）。
- **Hooks**：在 `useEffect`/`useLayoutEffect` 中注明**依赖项含义**与**与 DOM/布局相关的顺序**（先同步 class 再持久化等）。
- **与全局样式联动**：若依赖 `document.documentElement` 的 class 或 `index.css` 变量，在 **单一同步函数**处集中说明，避免在多处散写。

## Python

- **模块级**：`"""` 一段说明职责与主要入口（2～4 行内）。
- **公开 service 函数**（`async def` 被 router 或其它包调用）：一句说明返回语义；复杂时补充 **Raises** 或关键步骤（事务边界、`commit` 时机）。

## 风格

- 与现有文件一致：全角标点仅用于面向中文用户的字符串，**注释内标点**用半角与英文句首大写（句子简短时可小写起句，但同文件要统一）。
- 注释在代码**上方**或行尾极短注；不拆散可读的逻辑块去插大段说明。

## 与 Agent 的约定

- 为现有代码**补注释**时：优先**入口、持久化、事件、与 CSS 联动**等读者易漏的点；不批量给每个私有函数加模板注释。
- 新功能合入时：随 PR 带上的注释应**经得起删**：若实现改了，这段注释是否仍真；过时注释优先改或删。
