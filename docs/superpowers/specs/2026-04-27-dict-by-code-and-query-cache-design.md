# 按 `dict_code` 拉取数据字典（含树形子项）与前端 Query 统一方案

**日期**：2026-04-27  
**状态**：已评审待实现  
**范围**：后端在现有 `GET /workspaces/{workspace_id}/dicts` 上增加可选 `code` 查询，并在有值时**在单响应内**返回多级 `item_tree`；`minerva-ui` 增加 `@tanstack/react-query`，以 **Query 为全站数据缓存与去重基座**，并提供可在表单、表格中复用的字典能力（`useQuery` + 小组件/Hook）。

**设计依据（对话）**：`code` 过滤 + 响应 B（同包 `item_tree`）+ 多级树；全站采用 **方案 2（TanStack Query）**。

---

## 1. 目标与成功标准

- **传 `dict_code` 即得可用数据**：一次 `GET`（带 `code`）即可得到该工作空间下该字典的**表头信息** + **子项树**（`parent_uuid` 成树，与 `DictionaryPage` 现有展平→组树语义一致），避免「先 list 全量主表再按 id 拉 items」的附加往返。
- **少重复请求**：同一路由/同屏多组件、多列表列复用同一 `dict_code` 时，在 **Query 去重** 下仅发起**一次**网络请求（在 `staleTime` 内复用缓存）。
- **全站统一**：`minerva-ui` 在根布局挂载 **`QueryClientProvider`**，新特性及后续页面优先用 `useQuery` / `useMutation` + `queryClient.invalidateQueries` 管缓存失效，不引入并行的自研全局 Request 缓存层。
- **适用场景**：表单（`Select` / `TreeSelect` 等，按产品选择）、表格列将存库的 **item `code` 转 `name`** 展示。

---

## 2. 后端 API 合同

### 2.1 现有端点行为扩展

- **方法 / 路径**：`GET /workspaces/{workspace_id}/dicts`（不变）。
- **鉴权**：与现有一致：`get_current_user` + `require_workspace_member`。

### 2.2 查询参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `page` | int，≥1 | 与现有一致。 |
| `page_size` | int，在允许范围内 | 与现有一致。 |
| `code` | string，**可选** | 有值时：按**当前 workspace** 下 `dict_code`（trim 后**精确**匹配）**过滤**主表行；不区分大小写与否：**与数据库比较方式一致，建议与写入时 `strip` 后存储一致，匹配时 trim**（实现计划写死）。 |

### 2.3 当**未**传 `code`

- 行为与**当前**列表分页一致；响应中每条 `SysDictListItem` **不包含**子项树字段（与现有 `SysDictListItemOut` 兼容）。

### 2.4 当**传入** `code`

- **过滤结果**：`total` 为匹配到的**字典主表**行数，取值 **0 或 1**（`workspace_id + dict_code` 唯一）。
- **`items`**：当前页上字典主表行列表；当 `code` 有值时，预期仅 `page=1` 且 `page_size>=1` 时命中；若 `page>1` 或超出范围，可为空，但 **`total` 仍表示「是否存在该 `dict_code` 的字典」**（与「过滤后总条数」一致，**推荐**：有 `code` 时 `total` 为 0 或 1，不随 `page` 误增）。
- **嵌套字段名**：在 `SysDictListItemOut` 上增加**可选**字段 **`item_tree: list[SysDictItemNodeOut]`**（名称写死，前后端统一）。
  - 当**不存在**该 `dict_code`：`items: []`，`total: 0`。
  - 当**存在**且页内含有该主表行：该行带 **`item_tree`**，为**根节点列表**；每个节点为：

**`SysDictItemNodeOut`（recursive）**

- 与现有一致的基础字段：`id`, `dict_uuid`, `parent_uuid`, `code`, `name`, `item_sort`, `create_at`, `update_at`（与 `SysDictItemOut` 对齐，避免重复造字段名）。
- **`children: list[SysDictItemNodeOut]`**：子节点；叶节点为 `[]`。
- **排序**：与仓储 `list_items_for_dict` 的排序一致，再在内存中**组树**（与前端 `buildItemTree` 逻辑对齐）；保证同一父下顺序稳定。

### 2.5 HTTP 与错误

- 未知 `code`：**200** + 空列表 + `total: 0`（不暴露是否存在其他字典）。
- 服务错误：按现有 `AppError` / HTTP 约定。

### 2.6 服务层

- 复用已有 `list_items_by_dict_code` 取**扁平**列表，在 API 或 service 层**组树**后输出；避免重复 SQL 与语义分叉。

---

## 3. 前端：`@tanstack/react-query`

### 3.1 依赖与挂载

- 在 `minerva-ui` 增加依赖 **`@tanstack/react-query`**（版本与 React 18 兼容的最新稳定主版本，实现计划里锁版本号）。
- 在 **`/app` 有鉴权、需拉业务数据的布局**上挂载 `QueryClientProvider`（与 `ConfigProvider` 并列或外层均可，**单一** `QueryClient` 实例，放在 `main.tsx` 或 `AppThemedLayout` 上择一、实现计划定稿）。
- **默认 `QueryClient` 配置**（可在实现中微调，spec 定原则）：
  - **`staleTime`**：字典类只读数据可设 **1～5 分钟**（如 `3 * 60 * 1000`），减少重复请求；**`gcTime`（原 cacheTime）** 略大于 `staleTime`。
  - **`retry`**：对网络类失败有限次重试；4xx 不重试（与 `apiJson` 行为配合）。

### 3.2 Query Key 约定

- 列表（按 code）示例：`['dict', workspaceId, 'byCode', dictCode, { page, pageSize }]`，其中 **`workspaceId` 用字符串 UUID**，避免对象引用导致无效去重。
- 若同页仅关心「带 `code` 的第一页树」，可固定 `page: 1, pageSize: 100` 与后端约定一致（与现分页常量对齐时可引用 `minerva-ui/src/constants/pagination`）。

### 3.3 API 层（`src/api/dicts.ts`）

- 新增/扩展 `listDicts` 的 params：`code?: string`。
- 类型：`SysDictListItem` 上增加可选 `item_tree?: SysDictItemNode[]`；`SysDictItemNode` **递归** `children`。
- 封装 **`fetchDictByCode(workspaceId, dictCode)`**（内部即带 `code` 的 `listDicts`），供 `queryFn` 使用。

### 3.4 可复用模块

- **`useDictItemTree(dictCode: string, options?)`**：封装 `useQuery`，`enabled: Boolean(workspaceId)`，从 `useAuth` 取 `workspaceId`。
- **`DictText`**：props：`dictCode`, `value`（存库的 item `code`），内部用 `useDictItemTree` 或子 hook 在**扁平化 Map** 上反查 `name`；无匹配则回退显示 `value` 或 `-`（实现计划写死）。
- **`DictSelect` / 树形封装**（可分期）：`dictCode` + 表单受控；多级用 `TreeSelect`，选项由 `item_tree` 转换；`fieldNames` 与 `code`/`name` 对齐 Ant Design 要求。

### 3.5 缓存失效

- 在 **字典主表/明细写操作成功** 后（`DictionaryPage` 内 `createDict` / `patchDict` / `deleteDict` / 子项 `create`/`patch`/`delete` 等），对**受影响**的 `dict_code` 调用 **`queryClient.invalidateQueries({ queryKey: ['dict', workspaceId, 'byCode', affectedCode] })`**；若变更可能影响「整表列表」，可额外 invalidate `['dict', workspaceId]` 前缀下列表 query（实现计划按改动面最小化）。

---

## 4. 测试

- **后端**：`?code=` 存在 / 不存在；`item_tree` 为树且顺序符合预期；无 `code` 时响应形状与改前兼容（集成测试风格对齐 `test_dict_api`）。
- **前端**：可选 E2E/组件测试验证「同 `dictCode` 多挂载只请求一次」（依赖 mock fetch 或 MSW，实现计划评估成本）。

---

## 5. 非目标（本 spec 不覆盖）

- 不强制迁移现有所有页面到 Query（**渐进**；新字典消费与本次改动路径优先用 Query）。
- 不在本 spec 内规定「全站 `staleTime` 黄金数值」，仅规定字典类读接口的**原则**与失效策略。

---

## 6. 与既有文档关系

- 数据表与主从 CRUD 见 `2026-04-25-dictionary-management-design.md`；本 spec 在其上增加**只读聚合查询**与 **UI 复用/Query 化** 约定。
