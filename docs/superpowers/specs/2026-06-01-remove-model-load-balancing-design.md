# 移除模型供应商 load_balancing_enabled 字段设计

**日期**：2026-06-01  
**状态**：已实现（2026-06-01）  
**范围**：从 `sys_models` 表及全栈（后端 API、管理端 UI、测试）彻底移除 `load_balancing_enabled`（负载均衡）字段及其所有引用。

**关联文档**：

- `docs/superpowers/specs/2026-04-25-model-providers-management-design.md`（模型供应商 CRUD 基线；该字段原在此引入）
- `docs/superpowers/specs/2026-05-28-llm-multi-capability-design.md`（已明确不实现负载均衡）

---

## 1. 目标与成功标准

### 1.1 目标

- 删除 `sys_models.load_balancing_enabled` 数据库列。
- 后端 model-provider CRUD API 不再接受或返回该字段。
- 管理端「模型供应商」页面移除表格列、表单项、详情展示及 inline 切换逻辑。
- 清理 i18n 文案与测试 fixture 中的相关引用。

### 1.2 动机

`load_balancing_enabled` 自模型供应商 CRUD 上线起仅作为配置/UI 字段存在，**从未参与运行时逻辑**：

- `ModelResolver` / `ResolvedModel` 不读取该字段。
- `2026-05-28-llm-multi-capability-design` 非目标中已声明「不实现 `load_balancing_enabled` 负载均衡」。

保留该字段易误导用户以为已支持负载均衡，应彻底移除。

### 1.3 成功标准

- Alembic migration 执行后，`sys_models` 无 `load_balancing_enabled` 列。
- `schema_postgresql.sql` 与 ORM 模型一致。
- 模型供应商 API 的请求/响应 JSON 不含 `load_balancing_enabled`。
- `ModelProvidersPage` 无负载均衡相关 UI。
- 相关后端测试通过。

### 1.4 需求决策摘要

| 项 | 决策 |
|----|------|
| 数据库 | **彻底删列**（Alembic `DROP COLUMN` + 同步 `schema_postgresql.sql`） |
| 实施方式 | **单次 PR** 同步改 DB、后端、前端、测试 |
| API 兼容 | 破坏性变更；仅内部管理端消费，无外部客户端 |
| 历史 plan/spec | 归档文档不修改；基线 spec 追加修订说明 |

---

## 2. 数据库迁移

### 2.1 Alembic revision

- **down_revision**：当前 HEAD `c5d6e7f8a9b0`（`sys_ocr_tool_api_key_len`）。
- **upgrade**：

```python
op.drop_column("sys_models", "load_balancing_enabled")
```

- **downgrade**：

```python
op.add_column(
    "sys_models",
    sa.Column(
        "load_balancing_enabled",
        sa.Boolean(),
        server_default=sa.text("false"),
        nullable=False,
    ),
)
```

### 2.2 schema_postgresql.sql

删除以下内容：

- `CREATE TABLE sys_models` 中的 `load_balancing_enabled bool DEFAULT false NOT NULL` 行。
- `COMMENT ON COLUMN public.sys_models.load_balancing_enabled IS '负载均衡'` 行。

### 2.3 数据影响

既有行中该列的值（均为 `true`/`false`）随列删除而丢弃，无业务影响。

---

## 3. 后端变更

| 文件 | 变更 |
|------|------|
| `backend/app/sys/model_provider/domain/db/models.py` | 删除 `load_balancing_enabled` ORM 映射 |
| `backend/app/sys/model_provider/api/schemas.py` | 从 `ModelProviderCreateIn`、`ModelProviderPatchIn`、`ModelProviderListItemOut`、`ModelProviderDetailOut`、`ModelProviderGroupItemOut` 移除字段 |
| `backend/app/sys/model_provider/api/router.py` | 移除 mapper 与 create body 中的字段引用 |
| `backend/app/sys/model_provider/service/model_provider_service.py` | `create_model` 不再写入该字段 |

`update_model` 通过 `patch` dict 泛化 `setattr`；schema 移除后 PATCH 不再接受该 key，无需额外过滤逻辑。

---

## 4. 前端变更

| 文件 | 变更 |
|------|------|
| `frontend/src/api/modelProviders.ts` | `ModelProviderGroupItem`、`ModelProviderCreatePayload`、`ModelProviderPatchPayload` 移除字段 |
| `frontend/src/features/settings/model-providers/ModelProvidersPage.tsx` | 删除：表格列、`handleToggleLoadBalancing`、表单 `Form.Item`、详情 `Descriptions.Item`、form 默认值与 submit 映射 |
| `frontend/src/i18n/locales/zh-CN.json` | 删除 `settings.modelProvidersColLb`、`settings.modelProvidersFieldLb` |
| `frontend/src/i18n/locales/en.json` | 同上 |

表格 `tableScrollX` 可酌情从 1400 减至约 1300（非必须）。

---

## 5. 测试

| 文件 | 变更 |
|------|------|
| `backend/tests/test_llm_model_resolver.py` | `SysModel` fixture 构造去掉 `load_balancing_enabled=False` |

若存在 model-providers API 集成测试断言该字段，同步移除断言。

---

## 6. 文档回填

- 本文档为本次变更的设计 spec。
- 在 `docs/superpowers/specs/2026-04-25-model-providers-management-design.md` 末尾追加 **§11 修订记录**，说明 `load_balancing_enabled` 已于 2026-06-01 移除，详见本文档。
- 历史 plan 文件（`2026-04-25-model-providers-crud.md`、`2026-05-28-llm-multi-capability.md`）保持归档，不修改。

---

## 7. 兼容性与错误处理

- **API**：移除字段后，旧版前端若仍发送 `load_balancing_enabled`，Pydantic v2 默认 `extra='ignore'`，请求体中多余字段被忽略，不会 422。
- **Migration 顺序**：先跑 migration 再部署新代码；若新代码先部署而 DB 仍有列，ORM 未映射该列不影响读写（SQLAlchemy 忽略未映射列）；若 migration 先跑而新代码未部署，旧代码读写会失败——**标准做法：migration 与应用同批发布**。
- **回滚**：downgrade 恢复列，默认 `false`。

---

## 8. 非目标

- 不实现任何负载均衡逻辑。
- 不修改 `app/llm`、`app/agent` 运行时选模逻辑。
- 不修改其它与 `sys_models` 无关的模块。

---

## 9. 自检记录（定稿）

- [x] 无 `TODO` / `TBD` 占位。
- [x] 数据库、后端、前端、测试、文档范围完整且一致。
- [x] 与 `2026-05-28-llm-multi-capability-design` 非目标对齐。
- [x] 单次 PR 策略明确，可直接进入实现计划。

---

## 10. 实现对照

| 项 | 代码 |
|----|------|
| Migration | `backend/alembic/versions/f6a7b8c9d0e1_drop_sys_models_load_balancing_enabled.py` |
| SQL 补丁 | `backend/sql/patches/2026-06-01-drop-sys-models-load-balancing-enabled.sql` |
| 后端 | `backend/app/sys/model_provider/` |
| 前端 | `frontend/src/features/settings/model-providers/ModelProvidersPage.tsx` |
