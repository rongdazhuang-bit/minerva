# district

通过高德行政区域查询 API 按关键词查询 adcode 与区划层级（禁止编造区划）。

## 何时使用

**Planner 必选本 skill（`skill_id=district`）**：用户询问某地的行政区划、下属区县、adcode 等信息。

**子 Agent 执行**：须调用 `search_district_tool`；需要下级区划时将 `subdistrict` 设为 1/2/3。

## Planner 路由

- 行政区
- 区划
- 哪个区
- 有哪些区
- 有哪些县
- 下属区域
- 下辖

## 工具

| 工具 | 说明 |
|------|------|
| `search_district_tool` | 必填 `keywords`；可选 `subdistrict`（0=仅本级，1/2/3=下级层数）。返回 JSON：`ok`, `districts[]`（含 name/adcode/level/center）。 |

## 回答要求

- 无匹配结果时提示用户补充更精确的地名。
- 用简洁中文列出相关区划名称与 adcode。
