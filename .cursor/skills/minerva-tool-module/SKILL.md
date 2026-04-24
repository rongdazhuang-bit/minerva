---
name: minerva-tool-module
description: >-
  Use when adding backend code under `app/tool`, scaffolding a new feature next to
  `app/tool/ocr`, or replicating the Minerva tool-module layout: copy the exact
  directory tree of `backend/app/tool/ocr` and place domain/application/
  infrastructure/api code accordingly.
---

# Minerva 工具模块：以 `app/tool/ocr` 为模板的代码结构

## 规范来源

本项目的**标准代码结构**以仓库内**已存在**的目录为唯一范本：

- **范本根目录**：`backend/app/tool/ocr/`
- **父包**：`backend/app/tool/`（`__init__.py` 表示 `app.tool` 为工具集成包）

新增任何工具型能力时：**先对照 `app/tool/ocr` 的目录名与子包划分**，再建 `app/<新模块名>/`，子目录**与 ocr 同级同名**，不在别处发明平行结构（除非经架构变更讨论后更新本 Skill）。

## 参考目录（仓库现状，与 ocr 一致则合规）

`backend/app/tool/`：

```text
app/tool/
  __init__.py
  ocr/
    __init__.py
    domain/
      __init__.py
    domain/db
      __init__.py
    domain/dto
      __init__.py
    domain/vo
      __init__.py
    service/
      __init__.py
    infrastructure/
      __init__.py
    utils/
      __init__.py
    api/
      __init__.py
```

以上路径在导入时为：`app.tool.ocr` → `app.tool.ocr.domain` / `api` / `service` / `utils`。

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

## 子目录职责（与 ocr 四层对齐）

| 子目录                | 职责                                                                                |
|--------------------|-----------------------------------------------------------------------------------|
| **domain**         | 领域模型、规则、领域异常；可含对外部系统的抽象（如 `Protocol`），不直接依赖具体 HTTP 库或 ORM 实现细节。                   |
| **service**        | 用例与应用服务；编排 `domain` 与通过端口调用的能力，不直接写传输层。                                           |
| **infrastructure** | 端口实现、外部 API 客户端、持久化适配等；可依赖 `domain.db` 的 DB、配置等**项目已有**能力。                        |
| **api**            | FastAPI 路由、Pydantic 入参/出参、本模块 `deps`；在 `app/api/router.py` 中 `include_router` 挂接。 |
| **utils**          | 模板内具体工具类实现                                                                        |

与全局 `app/domain`、`app/infrastructure` 的边界：**可复用则 import**；**仅本工具使用**的代码放在 `app/tool/<name>/` 下。

## 增量文件应落在哪一层

在保持**上述五子包始终存在**的前提下，按需增加文件（命名与 ocr/本仓库其他模块风格一致）：

- `api/router.py`、`api/schemas.py`、`api/deps.py`（常见）
- `application/service.py` 等
- `domain/models.py` 等
- `infrastructure/` 下客户端、仓储

不在 `domain` 中写 FastAPI 依赖或 `Request` 处理逻辑。

## 检查清单

1. 新建 `app/tool/<name>/` 时，**子目录与 `app/tool/ocr` 一一对应**（五层 + 根 `__init__.py`）。
2. 业务代码按上表落层；跨层依赖方向为 **api → application → (domain, infrastructure 实现)**，**domain 不依赖 api**。
3. 路由在 `app/api/router.py` 注册；配置走 `app/config.py` 等，密钥不进仓库。
4. 持久化/迁移遵守仓库 `alembic`、`sql/` 习惯。
5. 注释规约见 `.cursor/skills/code-comments/SKILL.md`。

## 与 `app/domain/identity` 等目录的关系

`app/domain/*` 多为**按领域水平切分**；`app/tool/<name>` 为**单工具垂直切片**（以 ocr 为范式的全栈目录）。**新的外部工具/能力集成**优先放在 `app/tool/`，与 ocr 同构；若多工具共享同一领域模型，再考虑上提到 `app/domain` 并重构。

## OCR 工具管理页（前端）滚动规则

当实现或调整 `minerva-ui/src/features/settings/OcrSettingsPage.tsx` 表格时，遵循以下两条固定规则：

1. **右侧页面不滚动**：保持外层容器 `overflow: hidden`，不要让主内容区随表格数据量出现整页纵向滚动。
2. **仅表格体滚动 + 表头固定**：表格使用 `scroll.y`（限制表格体高度）和 `sticky`（固定表头），确保大量数据时只滚动表格内容区。
3. **滚动条按需显示**：表格体滚动容器使用 `overflow: auto`，默认不展示滚动条，仅在内容溢出时显示（避免常驻滚动条影响视觉）。
