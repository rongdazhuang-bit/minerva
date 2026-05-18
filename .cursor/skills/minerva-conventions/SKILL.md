---
name: minerva-conventions
description: >-
  Minerva 仓库级开发约定：(1) 数据库表设计禁止外键与 ON DELETE 级联，关联与删除在业务代码层实现；
  (2) 修 bug/改行为时先查 docs/superpowers/specs 与设计文档，改代码后再回填修订文档。
  Use when designing tables, writing schema/SQL/ORM, implementing delete APIs, cascading cleanup,
  or when fixing bugs, aligning code with specs, or updating requirements/design docs after code changes.
  Triggers: 外键、级联删除、CASCADE、RESTRICT、schema、建表、删除接口、需求文档、设计文档、spec 回填.
---

# Minerva 项目约定

## 1. 数据库：禁止外键与库层级联

### 规则（硬性）

- 设计或修改表结构时，**不得**在 PostgreSQL / `backend/sql/` 中声明 `FOREIGN KEY`、`REFERENCES`、`ON DELETE CASCADE`、`ON DELETE SET NULL`、`ON DELETE RESTRICT` 等库级关联与级联。
- SQLAlchemy ORM 中 **不得** 使用 `ForeignKey(..., ondelete=...)`；关联字段使用 `UUID`（或等价类型）列 + **索引** 即可，在注释/docstring 中说明逻辑引用哪张表。
- **删除、清空、阻止删除**（原 CASCADE / RESTRICT / SET NULL 语义）必须在 **service / repository** 等业务层显式实现，并在对应 API 或内部流程中调用。

### 仓库现状（对照）

| 项 | 位置 |
|----|------|
| 无 FK 的建表脚本 | `backend/sql/schema_postgresql.sql`（文件头有约定说明） |
| 已有库移除外键 | `backend/sql/patches/drop-foreign-keys.sql` |
| 示例：Agent 会话删除 | `backend/app/agent/infrastructure/repository.py` → `delete_agent_session` |
| 示例：字典删除 | `backend/app/sys/dict/service/dictionary_service.py` → `delete_dict` |
| 示例：OCR 任务删除 | `backend/app/file_ocr/service/ocr_file_delete.py` → `delete_ocr_file_dependents` |
| 示例：模型删除前校验 | `backend/app/sys/model_provider/service/model_provider_service.py` → `delete_model` |

### 实现删除时的检查清单

1. 列出该主表在业务上「拥有」的子表 / 冗余行（日志、结果页、消息、run 节点等）。
2. 在 **同一事务** 内按「子表 → 主表」顺序 `delete()` / `session.execute(delete(...))`，或使用明确的批量清理函数。
3. 原 RESTRICT 语义（不允许删父若仍有子）→ 删除前 `count` / 查询，返回 **409** 等业务错误，**不要**依赖数据库报错。
4. 原 SET NULL 语义 → 删除父行前对相关行 `update(..., values(null))`。
5. 新增表或删除 API 时，**不要**在 spec 中写「依赖外键级联」；在 spec 的「实现对照」中写明代删顺序与代码路径。

---

## 2. 改代码前先对文档，改完回填文档

### 规则（硬性）

修复缺陷、调整行为或做与产品相关的实现时，顺序必须为：

1. **先定位文档**：在 `docs/superpowers/specs/` 中查找对应 `*-design.md`（及关联 plan）；Agent 模块可对照 `docs/agent-module-design.md`。无 spec 时先与用户确认是否新建 spec，再写代码。
2. **再改代码**：实现须与文档描述一致；若文档过时，以**即将达成的正确行为**为准，并在第 3 步修正文档。
3. **最后更新文档**：将需求/设计 spec 的 **状态**、**实现对照**（建议章节名：`实现对照（以代码为准，YYYY-MM-DD）`）及正文里与代码不一致的 API、表名、删除策略等 **回填修订**；**不以「代码为准」为借口长期不写 spec**。

### 文档位置

| 类型 | 路径 |
|------|------|
| 功能设计 spec | `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` |
| 实现计划（可选） | `docs/superpowers/plans/` |
| Agent 技术说明 | `docs/agent-module-design.md` |

### 回填时最少更新内容

- 文首 **状态**（如：已实现 / 部分实现 / 已废止）。
- 与本次改动相关的 API 路径、请求字段、表名、**删除/级联策略（应用层）**。
- 新增 **实现对照** 表：spec 条目 | 当前代码位置 | 备注（含未做项）。

### 禁止

- 未读 spec 直接大改行为后在 PR 中不更新任何 `docs/`。
- 在 spec 中继续写「`ON DELETE CASCADE`」「依赖外键」等库级策略（除非明确标注为**历史/已废止**）。

---

## 3. 与其他 Skill 的关系

- **注释与目录**：`/.cursor/skills/code-comments/SKILL.md`（类/方法注释、`app/sys/tool` 分层、分页与 UI 约定）。
- **本 Skill**：库表无外键 + 文档驱动修改闭环。

两者同时适用时，均应遵守。
