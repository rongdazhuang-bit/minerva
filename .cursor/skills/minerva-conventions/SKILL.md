---
name: minerva-conventions
description: >-
  Minerva 仓库级开发约定：(1) 数据库表设计禁止外键与 ON DELETE 级联，关联与删除在业务代码层实现；
  (2) 修 bug/改行为时先查 docs/superpowers/specs 与设计文档，改代码后再回填修订文档；
  (3) 环境变量在 app/config.py 或代码中新增/删除/更名/改默认值时，须同步 backend/.env.example 与 backend/.env.dev；
  (4) minerva-ui 所有二次确认统一使用 Ant Design Popconfirm，禁止 Modal.confirm 等替代。
  Use when designing tables, writing schema/SQL/ORM, implementing delete APIs, cascading cleanup,
  changing Settings or os.getenv, fixing bugs, aligning code with specs, updating requirements/design docs after code changes,
  or adding minerva-ui destructive actions and confirmation UX.
  Triggers: 外键、级联删除、CASCADE、RESTRICT、schema、建表、删除接口、需求文档、设计文档、spec 回填、环境变量、.env、Settings、config.py、Popconfirm、二次确认、Modal.confirm、退出登录.
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

## 3. 环境变量：同步 `.env.example` 与 `.env.dev`

### 规则（硬性）

在 backend 中**新增、删除、更名或修改默认值/语义**的环境变量时，必须在**同一 PR / 同一次改动**内同步更新：

| 文件 | 用途 |
|------|------|
| `backend/.env.example` | 模板：占位符、本地 docker-compose 默认连接串、分组注释；**不含**真实密钥 |
| `backend/.env.dev` | 团队/本地开发实际值；保留已有连接串与密钥，仅随代码变更增删改对应键 |

**不得**只改 `app/config.py`（或 `os.getenv`）而不同步上述两个文件。

### 何谓「环境变量变更」

以下任一情况均须同步：

1. **`app/config.py` `Settings` 字段**：增删字段、`Field(validation_alias=...)` 更名、默认值或 `description` 含义变化。
2. **代码内直接读取**：`os.environ.get` / `os.getenv`（如 `MINERVA_CELERY_USE_PREFORK`）。
3. **启动脚本约定**：`scripts/run-backend.*`、`scripts/run-celery.*` 文档化变量（`MINERVA_BACKEND_PORT`、`APP_ENV` profile）。

以下**通常不需要**写入 `.env.dev`（可仅在 `.env.example` 末尾以注释说明）：

- 操作系统级 `TZ`（除非团队统一要求写入 dev 配置）。

### 两个文件的分工

| 操作 | `.env.example` | `.env.dev` |
|------|----------------|------------|
| **新增** Settings 项 | 写入键 + 与 `config.py` 一致的默认值 + 中文注释 | 写入键；有团队共用非默认 dev 值则填写，否则与默认值相同 |
| **删除** | 删除对应行及注释 | 删除对应行 |
| **更名** | 旧键删除、新键写入 | 同左；保留原 dev 侧取值迁移到新键 |
| **仅改默认值** | 更新示例默认值 | 若 dev 未显式覆盖可不动；若 dev 曾手写旧默认则改为新默认或保留 intentional override 并加注释 |

### 格式与来源

- **键名**：与 `Settings` 的 `validation_alias` 或 Pydantic 大写蛇形名一致（如 `DATABASE_URL`、`AGENT_MAX_PLAN_STEPS`）。
- **分组**：按「运行环境 / 数据库 / JWT / AI / Celery / Agent」等区块排列，与现有 `.env.example` 结构一致。
- **权威来源**：`backend/app/config.py`；辅助检索 `os.getenv`、`scripts/run-backend.sh`。
- **加载顺序**（写入 `.env.example` 头注释即可，勿重复发明）：进程环境变量 → 单个 `backend/.env.<APP_ENV>`（无叠加；脚本无参默认 `local` → `.env.local`）。
- **勿**在配置文件中添加应用未读取的键（历史 `REDIS_URL` 若仅备忘，须注释说明「应用不读取，以 `CELERY_*` 为准」）。

### 实现时的检查清单

1. 改 `config.py` 或 `os.getenv` 后，列出所有受影响的环境变量键名。
2. 更新 `backend/.env.example`（含分组注释；脚本/测试专用项可注释列出）。
3. 更新 `backend/.env.dev`（保留现有数据库/Redis/JWT 等真实 dev 值，不无故覆盖）。
4. 若 spec / `docs/agent-module-design.md` 等文档列出了环境变量表，**一并回填**（见 §2）。
5. 本地可执行：`cd backend && set APP_ENV=dev && python -c "from app.config import settings; print(settings.app_env)"` 确认 profile 与对应 `.env.<profile>` 加载无误。

### 禁止

- 合并仅含 `config.py` 变更、未更新 `.env.example` / `.env.dev` 的 PR（除非用户明确声明暂不维护 env 文件并记录 follow-up）。
- 在 `.env.example` 中提交生产密钥或团队成员真实密码。
- 新增 `Settings` 字段却只在 README 中说明、不写 env 文件。

---

## 4. minerva-ui：二次确认统一使用 Popconfirm

### 规则（硬性）

- 在 `minerva-ui` 中，凡需用户**二次确认**的操作（删除、退出登录、不可逆提交、批量危险操作等），**必须**使用 Ant Design **`Popconfirm`**，将确认气泡锚定在触发控件上。
- **禁止**使用 `Modal.confirm`、`window.confirm` 或自定义全屏确认弹层作为常规二次确认手段（除非产品 spec 明确要求全屏阻断式对话框，且须在 PR 中说明例外原因）。

### 推荐写法

```tsx
<Popconfirm
  title={t('…Confirm')}
  okText={t('common.confirm')}  // 或业务动词，如 auth.logout
  cancelText={t('common.cancel')}
  onConfirm={() => void doAction()}
>
  <Button type="text" danger icon={<DeleteOutlined />} aria-label={t('…')} />
</Popconfirm>
```

- **`title`**：一句说明后果的问句或陈述（走 i18n，键名建议 `*.…Confirm`）。
- **`okText` / `cancelText`**：与项目现有页面一致；删除类危险操作可对确认按钮设 `okButtonProps={{ danger: true }}`。
- **触发元素**：须为可接收 ref 的单个 DOM 节点（通常为 `Button`）；图标按钮保留 `aria-label`。
- **异步 `onConfirm`**：若需 await 接口，返回 Promise；Popconfirm 会在 Promise 挂起时显示 loading。

### 仓库对照

| 场景 | 位置 |
|------|------|
| 退出登录 | `minerva-ui/src/app/layout/AppHeaderToolbar.tsx` |
| 删除字典 / 模型 / OCR 配置等 | `DictionaryPage.tsx`、`ModelProvidersPage.tsx`、`OcrSettingsPage.tsx` 等 |

### 实现检查清单

1. 新增危险按钮时，用 `Popconfirm` 包裹触发器，**不要**在 `onClick` 里调 `Modal.confirm`。
2. 文案键加入 `minerva-ui/src/i18n/locales/zh-CN.json` 与 `en.json`。
3. Code review：搜索 `Modal.confirm`，若无 spec 例外说明则要求改为 `Popconfirm`。

### 禁止

- 为「统一风格」在部分页面用 Popconfirm、部分用 Modal.confirm 混用。
- 无确认文案、仅依赖图标颜色的破坏性操作。

---

## 5. 与其他 Skill 的关系

- **注释与目录**：`/.cursor/skills/code-comments/SKILL.md`（类/方法注释、`app/sys/tool` 分层、分页、表单与滚动条等 UI 约定）。
- **本 Skill**：库表无外键 + 文档驱动修改闭环 + 环境变量配置文件同步 + **二次确认 Popconfirm**。

两者同时适用时，均应遵守。
