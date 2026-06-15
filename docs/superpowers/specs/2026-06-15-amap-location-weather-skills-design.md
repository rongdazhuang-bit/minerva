# 高德 IP 定位 / 行政区域 / 天气 Agent Skills 设计说明

**日期**：2026-06-15  
**状态**：已实现（2026-06-15 按代码回填）  
**范围**：在 `backend/app/agent/skills/` 新增三个 Agent 运行时 skill（`ip_location`、`district`、`weather`），通过共享 `amap_client` 调用高德 Web 服务 API；激活 `weather` 时 `skill_loader` 自动连带加载依赖 skill 的工具。

**参考文档**：
- [IP 定位](https://lbs.amap.com/api/webservice/guide/api/ipconfig)
- [行政区域查询](https://lbs.amap.com/api/webservice/guide/api/district)
- [天气查询](https://lbs.amap.com/api/webservice/guide/api-advanced/weatherinfo)

---

## 1. 目标与成功标准

### 1.1 目标

| Skill ID | 工具名 | 高德 API |
|----------|--------|----------|
| `ip_location` | `lookup_ip_location` | `GET /v3/ip` |
| `district` | `search_district` | `GET /v3/config/district` |
| `weather` | `get_weather` | `GET /v3/weather/weatherInfo` |

- 共享 HTTP 客户端模块 `backend/app/agent/infrastructure/amap_client.py`。
- 三个 skill 各注册 **一个** tool；激活 `weather` 时 `skill_loader` 自动加载 `ip_location`、`district` 的工具（A+C 方案）。
- API Key 通过环境变量 `AMAP_WEB_SERVICE_KEY` 注入，**禁止**硬编码或提交到 git。

### 1.2 天气查询决策链

子 Agent 执行 `weather` skill 时须按以下顺序（规则写入 `weather/SKILL.md`）：

```
用户消息是否包含明确地区名/城市名？
  ├─ 是 → search_district(keywords=地区) → 取首个匹配 districts[].adcode
  └─ 否 → lookup_ip_location() → 取 adcode
         ↓
get_weather(city_adcode=adcode, extensions=all)
```

默认 `extensions=all`：同时返回实况（`lives`）与预报（`forecasts`）。

### 1.3 成功标准

- 用户问「今天天气怎么样」→ Planner 路由 `weather` → IP 定位 → 返回实况 + 预报。
- 用户问「北京天气」→ 行政区查询 → 返回北京天气（实况 + 预报）。
- 用户问「我在哪」→ 仅 `ip_location` → 返回省市与 adcode。
- 用户问「济南有哪些区」→ 仅 `district` → 返回下级行政区列表。
- `AMAP_WEB_SERVICE_KEY` 未配置时，工具返回 `{"ok": false, "error": "..."}`，服务不崩溃。
- 单元测试覆盖 `amap_client` 与 skill 工具注册/依赖加载。

### 1.4 非目标

- 不支持国外 IP、台湾详细区划（高德 API 限制）。
- 不返回行政区边界 `polyline`（`extensions=base`）。
- 不做 IP/天气结果缓存。
- 不在 Cursor IDE skills（`.cursor/skills/`）中重复实现。

---

## 2. 方案选型

| 方案 | 说明 | 结论 |
|------|------|------|
| **A+C（采用）** | 共享 `amap_client`；三 skill 各一 tool；`weather` 激活时 loader 自动加载依赖 | **采用** |
| B | 仅 `weather` skill 内注册三个 tool | 不符合「三个 skill」需求 |
| C-only | 三 skill 完全独立，靠 Planner 同时激活 | 易漏加载依赖，weather 易失败 |

---

## 3. 配置与环境变量

### 3.1 Settings

在 `backend/app/config.py` 新增：

```python
amap_web_service_key: str = Field(
    default="",
    description="高德 Web 服务 API Key（IP 定位、行政区、天气）。",
    validation_alias=AliasChoices("AMAP_WEB_SERVICE_KEY", "amap_web_service_key"),
)
```

### 3.2 环境文件同步（minerva-conventions §3）

| 文件 | 内容 |
|------|------|
| `backend/.env.example` | `AMAP_WEB_SERVICE_KEY=`（空占位 + 注释说明用途） |
| `backend/.env.dev` | 填入团队 dev Key（**勿提交真实 Key 到公开仓库**） |

Key 缺失时，`amap_client` 各方法立即返回 `ok: false`，不发起 HTTP 请求。

---

## 4. 共享模块：`amap_client.py`

**路径**：`backend/app/agent/infrastructure/amap_client.py`

### 4.1 接口

```python
async def lookup_ip(*, ip: str | None = None) -> dict[str, Any]: ...
async def search_district(*, keywords: str, subdistrict: int = 0) -> dict[str, Any]: ...
async def get_weather(*, city_adcode: str, extensions: str = "all") -> dict[str, Any]: ...
```

### 4.2 实现要点

- HTTP：`httpx.AsyncClient`；Base URL `https://restapi.amap.com/v3/`。
- 超时：`connect=5s`，`read=10s`。
- 请求参数：`key` 来自 `get_settings().amap_web_service_key`；`output=JSON`。
- 响应校验：`status == "1"` 且 `infocode == "10000"` 为成功；否则 `ok: false` + `error` + 原始 `info`/`infocode`。
- 成功响应在 `ok: true` 基础上附带 API 原始字段（精简后保留业务所需字段）。

### 4.3 各 API 端点与关键字段

**IP 定位** — `GET /ip`

| 请求参数 | 说明 |
|----------|------|
| `key` | 必填 |
| `ip` | 可选；不传则定位请求方 IP |

| 成功返回字段 | 说明 |
|--------------|------|
| `province`, `city`, `adcode`, `rectangle` | 省市、城市编码、矩形范围 |

**行政区域查询** — `GET /config/district`

| 请求参数 | 说明 |
|----------|------|
| `key` | 必填 |
| `keywords` | 行政区名称 / citycode / adcode |
| `subdistrict` | 0=仅本级；1/2/3=下级层数；默认 0 |
| `extensions` | 固定 `base`（不取边界） |

| 成功返回字段 | 说明 |
|--------------|------|
| `districts[]` | `name`, `adcode`, `level`, `center`, 可选 `districts` 子节点 |

**天气查询** — `GET /weather/weatherInfo`

| 请求参数 | 说明 |
|----------|------|
| `key` | 必填 |
| `city` | 城市 adcode（来自 IP 或行政区查询） |
| `extensions` | 默认 `all`（实况 + 预报） |

| 成功返回字段 | 说明 |
|--------------|------|
| `lives[]` | 实况：weather, temperature, winddirection, windpower, humidity, reporttime |
| `forecasts[]` | 预报：casts[]（date, dayweather, nightweather, daytemp, nighttemp 等） |

---

## 5. Skill 包结构

```text
backend/app/agent/skills/
  INDEX.md                    # 新增三行条目
  ip_location/
    SKILL.md
    tools.py                  # register_tools → [lookup_ip_location]
  district/
    SKILL.md
    tools.py                  # register_tools → [search_district]
  weather/
    SKILL.md
    tools.py                  # register_tools → [get_weather]
```

### 5.1 工具 JSON 契约

与现有 skill（如 `datetime`）一致：返回 **JSON 字符串**。

**成功示例**：

```json
{"ok": true, "province": "山东省", "city": "济南市", "adcode": "370100"}
```

**失败示例**：

```json
{"ok": false, "error": "AMAP_WEB_SERVICE_KEY 未配置"}
```

### 5.2 `ip_location`

**`lookup_ip_location(ip: str | None = None) -> str`**

- `ip` 为空时不传 `ip` 参数，由高德解析请求方 IP。
- 成功：`ok, province, city, adcode, rectangle`。
- 局域网/非法 IP：`adcode` 可能为空；SKILL.md 要求 Agent 提示用户提供城市名。

**Planner 路由触发词**：我在哪、我的位置、当前 IP、IP 定位、ip location、where am i

### 5.3 `district`

**`search_district(keywords: str, subdistrict: int = 0) -> str`**

- `keywords` 必填。
- 成功：`ok, districts`（数组，含 name/adcode/level/center）。
- 无匹配：`ok: true, districts: []` 或 `ok: false`（按 API 响应区分）。

**Planner 路由触发词**：行政区、区划、哪个区、有哪些区、有哪些县、下属区域

### 5.4 `weather`

**`get_weather(city_adcode: str, extensions: str = "all") -> str`**

- `city_adcode` 必填（6 位 adcode 字符串）。
- `extensions` 默认 `"all"`（用户已确认方案 B：默认实况 + 预报）。

**SKILL.md 强制流程**（子 Agent 须遵守）：

1. 从用户消息提取地区名；有则 `search_district`，无则 `lookup_ip_location`。
2. 从结果取 `adcode`；为空则告知用户无法定位并请补充城市名。
3. 调用 `get_weather(city_adcode=adcode)`。
4. 用简洁中文汇报：当前实况 + 近几天预报要点。

**Planner 路由触发词**：天气、气温、温度、下雨、下雪、冷不冷、热不热、weather、forecast

---

## 6. `skill_loader` 依赖自动加载

### 6.1 依赖表

```python
_SKILL_TOOL_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "weather": ("ip_location", "district"),
}
```

### 6.2 加载逻辑

扩展 `load_tools_for_skill`（或新增 `load_tools_for_skill_with_deps`）：

1. 解析目标 skill_id 的依赖链（仅一层，无递归）。
2. 按顺序加载：依赖 skill tools → 目标 skill tools。
3. 按 `tool.name` 去重（后者覆盖前者，理论上无冲突）。
4. 单独加载 `ip_location` / `district` 时不触发依赖。

### 6.3 `build_skill_react_agent`

继续使用扩展后的加载函数，使 `weather` 子 Agent 可见三个 tool。

---

## 7. INDEX.md 更新

在 `general` 之前插入（天气类触发词优先于通用对话）：

```markdown
- `weather`：你是天气查询助手。须先通过 IP 或行政区定位取得 adcode，再调用 get_weather（默认含实况与预报），禁止编造天气。
- `district`：你是行政区域查询助手。按地名或关键词查询 adcode 与区划层级，须调用 search_district，禁止编造区划。
- `ip_location`：你是 IP 定位助手。查询 IP 所在省市与 adcode，须调用 lookup_ip_location，禁止编造位置。
```

---

## 8. 错误处理

| 场景 | 工具返回 | Agent 应对 |
|------|----------|------------|
| Key 未配置 | `ok: false, error: "AMAP_WEB_SERVICE_KEY 未配置"` | 告知服务未配置 |
| 局域网/国外 IP | `adcode` 为空 | 请用户提供城市名后走 district |
| 行政区无匹配 | `districts` 为空 | 请用户补充更精确地名 |
| 高德 API 失败 | `ok: false, infocode, error` | 告知暂时无法查询 |
| 网络超时 | `ok: false, error: "请求超时"` | 建议稍后重试 |

---

## 9. 测试

| 文件 | 覆盖 |
|------|------|
| `backend/tests/test_amap_client.py` | mock httpx：三 API 成功、API 业务失败、Key 缺失、超时 |
| `backend/tests/test_amap_skills.py` | 各 skill `register_tools` 工具名；`weather` 依赖加载后共 3 个 tool；工具名无重复 |

---

## 10. 实现对照（以代码为准，2026-06-15）

| Spec 条目 | 当前代码位置 | 备注 |
|-----------|--------------|------|
| amap_client | `backend/app/agent/infrastructure/amap_client.py` | 已实现 |
| Settings | `backend/app/config.py` → `amap_web_service_key` | 已实现 |
| env 同步 | `backend/.env.example`, `backend/.env.dev` | 已实现（Key 需本地填入） |
| ip_location skill | `backend/app/agent/skills/ip_location/` | 工具名 `lookup_ip_location` |
| district skill | `backend/app/agent/skills/district/` | 工具名 `search_district_tool` |
| weather skill | `backend/app/agent/skills/weather/` | 工具名 `get_weather_info` |
| skill_loader 依赖 | `backend/app/agent/infrastructure/skill_loader.py` → `_SKILL_TOOL_DEPENDENCIES` | 已实现 |
| INDEX.md | `backend/app/agent/skills/INDEX.md` | 已实现 |
| 单元测试 | `backend/tests/test_amap_client.py`, `backend/tests/test_amap_skills.py` | 9 tests passed |
