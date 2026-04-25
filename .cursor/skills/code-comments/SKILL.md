---
name: code-comments
description: >-
  Repository conventions: (1) when and how to write code comments in TypeScript/React
  and Python; (2) backend tool modules under `app/tool` with `backend/app/tool/ocr` as
  the layout template, including table scroll rules; (3) minerva-ui Ant Design forms:
  `allowClear` on text inputs and selects, and InputNumber limitations. Use when adding
  or editing comments, documenting APIs, reviewing comment quality, scaffolding
  `app/tool/<name>`, building settings/auth forms, or the user asks for
  注释规范、工具模块目录、表单可清除、或表格滚动.
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

### minerva-ui：Ant Design 表单可清除

在 `minerva-ui` 中，凡**用户可编辑、且清空在业务上成立**的字段，对支持该能力的组件应加 **`allowClear`**，有值时展示清除图标，便于一键置空；**不得**在业务上禁止清空的只读/强必选场景为凑规范而强行可清。

- 适用：普通 **`Input`**、**`Input.Password`**、**`Select`**、**`TreeSelect`** 等（与 antd 文档一致有 `allowClear` 的组件）。
- **不适用**：**`InputNumber`**（本仓库使用 **antd 6**：类型与实现**均无** `allowClear`）——不要给 `InputNumber` 写 `allowClear`，否则 **TypeScript 与构建会失败**；需「一键清数字」时单独封装，或与表单约定 `null` / `??` 默认值的交互一致，依靠键盘删空等。

## Python

- **模块级**：`"""` 一段说明职责与主要入口（2～4 行内）。
- **公开 service 函数**（`async def` 被 router 或其它包调用）：一句说明返回语义；复杂时补充 **Raises** 或关键步骤（事务边界、`commit` 时机）。

## 风格

- 与现有文件一致：全角标点仅用于面向中文用户的字符串，**注释内标点**用半角与英文句首大写（句子简短时可小写起句，但同文件要统一）。
- 注释在代码**上方**或行尾极短注；不拆散可读的逻辑块去插大段说明。

## 与 Agent 的约定

- 为现有代码**补注释**时：优先**入口、持久化、事件、与 CSS 联动**等读者易漏的点；不批量给每个私有函数加模板注释。
- 新功能合入时：随 PR 带上的注释应**经得起删**：若实现改了，这段注释是否仍真；过时注释优先改或删。

---

# Minerva 工具模块：以 `app/tool/ocr` 为模板的代码结构

## 规范来源

本项目的**标准代码结构**以仓库内**已存在**的目录为唯一范本：

- **范本根目录**：`backend/app/tool/ocr/`
- **父包**：`backend/app/tool/`（`__init__.py` 表示 `app.tool` 为工具集成包）

新增任何工具型能力时：**先对照 `app/tool/ocr` 的目录名与子包划分**，再建 `app/tool/<新模块名>/`，子目录**与 ocr 同级同名**，不在别处发明平行结构（除非经架构变更讨论后更新本 Skill）。

## 参考目录（仓库现状，与 ocr 一致则合规）

`backend/app/tool/`：

```text
app/tool/
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

以上路径在导入时为：`app.tool.ocr` → `app.tool.ocr.domain` / `api` / `service` / `utils` 等。

**新工具模块**将 `ocr` 整段换成 `<name>`，即：

```text
app/tool/<name>/
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

与全局 `app/domain`、`app/infrastructure` 的边界：**可复用则 import**；**仅本工具使用**的代码放在 `app/tool/<name>/` 下。

## 增量文件应落在哪一层

在保持**上述子包与 ocr 同构**的前提下，按需增加文件（命名与 ocr/本仓库其他模块风格一致）：

- `api/router.py`、`api/schemas.py`、`api/deps.py`（常见）
- `service/<name>_service.py` 等
- `domain/db/models.py` 等
- `infrastructure/` 下客户端、仓储

不在 `domain` 中写 FastAPI 依赖或 `Request` 处理逻辑。

## 检查清单

1. 新建 `app/tool/<name>/` 时，**子目录与 `app/tool/ocr` 一一对应**（含 `domain` 下 db/dto/vo 等子包时的惯例）。
2. 业务代码按上表落层；跨层依赖方向为 **api → service → (domain, infrastructure 实现)**，**domain 不依赖 api**。
3. 路由在 `app/api/router.py` 注册；配置走 `app/config.py` 等，密钥不进仓库。
4. 持久化/迁移遵守仓库 `alembic`、`sql/` 习惯。
5. 代码注释与文档串遵循本 Skill **前半部分**《代码注释规范》。

## 与 `app/domain/identity` 等目录的关系

`app/domain/*` 多为**按领域水平切分**；`app/tool/<name>` 为**单工具垂直切片**（以 ocr 为范式的全栈目录）。**新的外部工具/能力集成**优先放在 `app/tool/`，与 ocr 同构；若多工具共享同一领域模型，再考虑上提到 `app/domain` 并重构。

## 表格滚动规则

当实现或调整表格时，遵循以下固定规则：

1. **右侧页面不滚动**：保持外层容器 `overflow: hidden`，不要让主内容区随表格数据量出现整页纵向滚动。
2. **仅表格体滚动 + 表头固定**：表格使用 `scroll.y`（限制表格体高度）和 `sticky`（固定表头），确保大量数据时只滚动表格内容区。
3. **滚动条按需显示**：表格体滚动容器使用 `overflow: auto`，默认不展示滚动条，仅在内容溢出时显示（避免常驻滚动条影响视觉）。
