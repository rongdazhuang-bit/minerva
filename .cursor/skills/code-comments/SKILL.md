---
name: code-comments
description: >-
  Repository conventions: (1) mandatory comments on every class and method/function,
  plus variable documentation where required; (2) full 「注释说明规则」—scope, exclusions,
  templates, self-checklist, backlog strategy; (3) when and how to write code comments in TypeScript/React
  and Python; (4) backend tool modules under `app/sys/tool` with `backend/app/sys/tool/ocr` as
  the layout template, including table scroll rules; (5) minerva-ui Ant Design forms:
  `allowClear` on text inputs and selects, and InputNumber limitations; (6) paginated
  lists: default 10 per page (shared constants in `app/pagination.py` and
  `minerva-ui/src/constants/pagination.ts`). Use when adding
  or editing comments, documenting APIs, reviewing comment quality, scaffolding
  `app/sys/tool/<name>`, building settings/auth forms, enforcing comment rules repo-wide,
  or the user asks for
  注释规范、注释说明规则、工具模块目录、表单可清除、表格滚动、或分页条数.
---

# 代码注释规范（Minerva）

## 目标

用**少量、高信噪比**的注释，帮助后续阅读者理解**意图、约束与副作用**；不把注释当成第二份实现说明。

## 硬性规则（必须遵守）

以下为本仓库对 Agent 与人工提交的**最低文档要求**；与下文「什么时候写」表中「少写或省略」冲突时，以本节约束为准。

| 对象 | 要求 |
|------|------|
| **类** | 每个类须有注释：Python 使用类 docstring `"""..."""`；TypeScript/React 使用块注释 `/** ... */` 或等价形式，说明职责、边界或与父类/接口的关系。 |
| **方法 / 函数** | 每个方法及模块级函数须有注释（含 `private` / 以下划线开头的 Python 方法）：说明用途；若有参数或返回值且类型不足以表达契约，须写明含义或非显而易见的副作用。 |
| **变量说明** | **模块级常量**、**类属性（含 React `useState` 等持久状态若语义非字面可得）**须有简短说明（声明旁单行或类 docstring 中的字段列表）。**局部变量**：业务含义、单位、枚举语义或读者无法从右侧表达式一眼读出的命名须有行尾或紧邻注释；纯惯例短名（如循环 `i`、`idx`、临时 `tmp`）若上下文已足够清晰可省略。 |

违反上述硬性规则的变更应在合并前补齐；审查评论质量时仍适用下文「风格」与「什么时候写」中的高信噪比原则——**Mandatory does not mean boilerplate**：禁止复制标识符英文译文凑行数。

## 注释说明规则（完整，可直接交付对照）

本节把「写什么、写在哪、哪些豁免」写成可执行的条文；硬性粒度仍以一节为准。

### 适用范围（必须做注释的代码）

| 区域 | 路径模式 | 说明 |
|------|-----------|------|
| 后端应用 | `backend/app/**/*.py` | 业务与基础设施 Python 源码。 |
| 前端应用 | `minerva-ui/src/**/*.{ts,tsx}` | 页面、组件、hooks、API 封装等。 |

**不在此范围**：`node_modules/`、`dist/`、`__pycache__/`、锁文件、纯二进制；**测试代码**建议同等对待，但不与本 Skill 的「工具模块」条款混为一谈。

### 豁免或从简（仍须在 PR 中交代）

| 情形 | 做法 |
|------|------|
| `minerva-ui/src/vite-env.d.ts` | 保留 `/// <reference types="vite/client" />` 等三斜杠指令即可；无需为每个 `ImportMeta` 字段重复作文档 unless 自定义扩展。 |
| 纯 barrel `index.ts` / `index.ts` 仅 `export * from "./x"` | 模块顶部 **一行** `/** Re-exports ... */` 或等价注释即可，不要求对每个再导出逐一注解（导出目标的注释在原文件）。 |
| Python **仅** 空白、`from pkg import mod` 的 `__init__.py` | 单行 docstring：`"""Exports public symbols for package `<qualified name>`."""` 或说明留白 intentionally empty（若团队约定保留空文件）。 |
| SQL / Alembic 迁移 | 以分段 `--` 注释为主；不按「类/方法 docstring」句式强求。 |

### 写法模板（复制再改成真话）

**Python 模块（文件前几行内的第一段字面量字符串，或与 PEP 236 相容的布局）**

```python
"""One line: what this module owns (routers, settings, tokens, …)."""

from __future__ import annotations
```

若先有 `from __future__`，则模块 docstring 为其下一语句亦可。

**Python 类 / 函数**

```python
class Foo:
    """Role of this aggregate / SQLAlchemy model / schema."""

    def bar(self, x: int) -> str:
        """Turn ``x`` into … ; raises … when …"""
```

**Python 模块级名绑定**

```python
# Stable JWT signing algorithm for access and refresh tokens.
_ALGO = "HS256"
```

**TypeScript 导出函数 / 组件**

```tsx
/** Renders workspace overview metrics and shortcuts. */
export function OverviewPage() { ... }
```

**TS 常量 / 配置**

```ts
/** Axios/React Query defaults shared by API modules. */
export const queryClient = ...
```

### 自检清单（合并 / Agent 收尾）

1. **模块**：`backend/app` 下每个 `.py` 有可被发现的中文或英文模块 docstring（`"""…"""`）；TS/TSX 文件有可读的顶层块注释说明文件职责（单行即可）。
2. **类 / def**：均有注释；嵌套路由内层函数若为 Handler closure（如 `register_exception_handlers` 内）也需简要说明响应契约。
3. **变量**：模块常量、`settings`-级别以外的 `_FOO` 若要全局可读须有注释（见硬性规则）。
4. **一致性**：注释语种与本 Skill「语言」节一致；不粘贴过时实现的复述。

### 存量代码补齐策略（全仓统一补注释时）

- **增量**：凡触碰的文件顺带补齐缺注释的顶层符号（不要求在同 PR 改无关文件，但若改动已过红线则应补齐）。
- **专项**：按子树分批（例如 `app/rule`、`minerva-ui/src/features/rules`）提交，便于评审。
- **自动化**：可选自建脚本 AST 扫模块 docstring、或 ESLint `jsdoc/require-jsdoc` 仅对新代码启用——不在此 Skill 固定命令名，以免与仓库演进脱节。

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

- **硬性规则落地**：每个 **class**、每个函数（含 **函数组件**、`export const Foo = () => …`、类方法与模块顶层函数）须有注释；见上文「硬性规则」节。
- 对 **`export` 的函数/常量**：若行为非一目了然，用 **1～3 行**块注释或简短 JSDoc（`@param` 仅当类型不足以表达时）。
- **Hooks**：在 `useEffect`/`useLayoutEffect` 中注明**依赖项含义**与**与 DOM/布局相关的顺序**（先同步 class 再持久化等）。
- **与全局样式联动**：若依赖 `document.documentElement` 的 class 或 `index.css` 变量，在 **单一同步函数**处集中说明，避免在多处散写。

### minerva-ui：Ant Design 表单可清除

在 `minerva-ui` 中，凡**用户可编辑、且清空在业务上成立**的字段，对支持该能力的组件应加 **`allowClear`**，有值时展示清除图标，便于一键置空；**不得**在业务上禁止清空的只读/强必选场景为凑规范而强行可清。

- 适用：普通 **`Input`**、**`Input.Password`**、**`Select`**、**`TreeSelect`** 等（与 antd 文档一致有 `allowClear` 的组件）。
- **不适用**：**`InputNumber`**（本仓库使用 **antd 6**：类型与实现**均无** `allowClear`）——不要给 `InputNumber` 写 `allowClear`，否则 **TypeScript 与构建会失败**；需「一键清数字」时单独封装，或与表单约定 `null` / `??` 默认值的交互一致，依靠键盘删空等。

### minerva-ui：分页列表默认每页 10 条

凡**带服务端/接口分页**的 `Table` 或列表请求，**默认每页条数固定为 10**，与后端列表 API 的默认 `page_size` 一致。

- **前端**：自 `minerva-ui/src/constants/pagination.ts` 引用 **`DEFAULT_PAGE_SIZE`** 作为 `Table` 的 `pagination.pageSize` 与请求参数中的 `page_size` 初始值；**新建**分页列表时不得再写死其他数字（如 20）作为默认，除非有明确产品要求并同时改常量与相关 API 默认值。
- **后端**：自 `app.pagination` 引用 **`DEFAULT_PAGE_SIZE`** 作为 `Query(..., default=DEFAULT_PAGE_SIZE)` 等；新增分页列表端点沿用同一常量。
- **例外**：在客户端**循环拉全量**（如合并多页直到 `total` 满足）时，为减少往返可对单次请求使用**不超过**接口 `le` 上限的较大 `page_size`；这不改变「用户打开列表时看到的」默认 10 条约定。

## Python

- **硬性规则落地**：每个 **class**、每个 **def**（含 `_` 前缀私有方法）须有 docstring 或紧邻块注释；模块级变量与类属性须有说明（见「硬性规则」节）。
- **模块级**：`"""` 一段说明职责与主要入口（2～4 行内）。
- **公开 service 函数**（`async def` 被 router 或其它包调用）：一句说明返回语义；复杂时补充 **Raises** 或关键步骤（事务边界、`commit` 时机）。

## 风格

- 与现有文件一致：全角标点仅用于面向中文用户的字符串，**注释内标点**用半角与英文句首大写（句子简短时可小写起句，但同文件要统一）。
- 注释在代码**上方**或行尾极短注；不拆散可读的逻辑块去插大段说明。

## 与 Agent 的约定

- **硬性规则**：新建或修改的类、方法、须说明的变量必须符合上文「硬性规则」节；不得留下无注释的新增类/方法。
- 为现有代码**补注释**时：在遵守硬性规则前提下，优先**入口、持久化、事件、与 CSS 联动**等读者易漏的点；注释仍须简洁，避免空洞模板句。
- 新功能合入时：随 PR 带上的注释应**经得起删**：若实现改了，这段注释是否仍真；过时注释优先改或删。

---

# Minerva 工具模块：以 `app/sys/tool/ocr` 为模板的代码结构

## 规范来源

本项目的**标准代码结构**以仓库内**已存在**的目录为唯一范本：

- **范本根目录**：`backend/app/sys/tool/ocr/`
- **父包**：`backend/app/sys/tool/`（`__init__.py` 表示 `app.sys.tool` 为系统域下的工具集成包）

新增任何工具型能力时：**先对照 `app/sys/tool/ocr` 的目录名与子包划分**，再建 `app/sys/tool/<新模块名>/`，子目录**与 ocr 同级同名**，不在别处发明平行结构（除非经架构变更讨论后更新本 Skill）。

## 参考目录（仓库现状，与 ocr 一致则合规）

`backend/app/sys/tool/`：

```text
app/sys/tool/
  __init__.py
  ocr/
    __init__.py
    domain/
      __init__.py
      db/
        __init__.py
        models.py
      dto/
        __init__.py
      vo/
        __init__.py
    service/
      __init__.py
    infrastructure/
      __init__.py
    utils/
      __init__.py
    api/
      __init__.py
      router.py
      schemas.py
```

以上路径在导入时为：`app.sys.tool.ocr` → `app.sys.tool.ocr.domain` / `api` / `service` / `utils` 等。

**新工具模块**将 `ocr` 整段换成 `<name>`，即：

```text
app/sys/tool/<name>/
  __init__.py
  domain/__init__.py
  service/__init__.py
  utils/__init__.py
  api/__init__.py
  infrastructure/__init__.py
```

`domain` 下按需保留 `db` / `dto` / `vo` 等子包，与 ocr 一致。

## 子目录职责（与 ocr 分层对齐）

| 子目录 | 职责 |
|--------|------|
| **domain** | 领域模型、规则、领域异常；可含对外部系统的抽象（如 `Protocol`），不直接依赖具体 HTTP 库或 ORM 实现细节。 |
| **service** | 用例与应用服务；编排 `domain` 与通过端口调用的能力，不直接写传输层。 |
| **infrastructure** | 端口实现、外部 API 客户端、持久化适配等；可依赖 `domain.db` 的 DB、配置等**项目已有**能力。 |
| **api** | FastAPI 路由、Pydantic 入参/出参、本模块 `deps`；在 `app/api/router.py` 中 `include_router` 挂接。 |
| **utils** | 本模块内具体工具类实现。 |

与全局 `app/domain`、`app/infrastructure` 的边界：**可复用则 import**；**仅本工具使用**的代码放在 `app/sys/tool/<name>/` 下。

## 增量文件应落在哪一层

在保持**上述子包与 ocr 同构**的前提下，按需增加文件（命名与 ocr/本仓库其他模块风格一致）：

- `api/router.py`、`api/schemas.py`、`api/deps.py`（常见）
- `service/<name>_service.py` 等
- `domain/db/models.py` 等
- `infrastructure/` 下客户端、仓储

不在 `domain` 中写 FastAPI 依赖或 `Request` 处理逻辑。

## 检查清单

1. 新建 `app/sys/tool/<name>/` 时，**子目录与 `app/sys/tool/ocr` 一一对应**（含 `domain` 下 db/dto/vo 等子包时的惯例）。
2. 业务代码按上表落层；跨层依赖方向为 **api → service → (domain, infrastructure 实现)**，**domain 不依赖 api**。
3. 路由在 `app/api/router.py` 注册；配置走 `app/config.py` 等，密钥不进仓库。
4. 持久化/迁移遵守仓库 `alembic`、`sql/` 习惯。
5. 代码注释与文档串遵循本 Skill **前半部分**《代码注释规范》。

## 与 `app/domain/identity` 等目录的关系

`app/domain/*` 多为**按领域水平切分**；`app/sys/tool/<name>` 为**单工具垂直切片**（以 ocr 为范式的全栈目录）。**新的外部工具/能力集成**优先放在 `app/sys/tool/`，与 ocr 同构；若多工具共享同一领域模型，再考虑上提到 `app/domain` 并重构。

## 表格滚动规则

当实现或调整表格时，遵循以下固定规则：

1. **右侧页面不滚动**：保持外层容器 `overflow: hidden`，不要让主内容区随表格数据量出现整页纵向滚动。
2. **仅表格体滚动 + 表头固定**：表格使用 `scroll.y`（限制表格体高度）和 `sticky`（固定表头），确保大量数据时只滚动表格内容区。
3. **滚动条按需显示**：表格体滚动容器使用 `overflow: auto`，默认不展示滚动条，仅在内容溢出时显示（避免常驻滚动条影响视觉）。
