# weather

通过高德天气 API 查询指定城市的实况与预报天气（禁止编造天气）。

## 何时使用

**Planner 必选本 skill（`skill_id=weather`）**：用户询问天气、气温、是否下雨/下雪等。

**子 Agent 执行**：须先取得城市 `adcode`，再调用 `get_weather_info`。本 skill 激活时会同时加载 `lookup_ip_location` 与 `search_district_tool`。

## 决策流程（必须遵守）

1. 用户消息是否包含明确地区名/城市名？
   - **是** → 调用 `search_district_tool(keywords=地区名)` → 取首个匹配 `districts[].adcode`
   - **否** → 调用 `lookup_ip_location()` → 取 `adcode`
2. 若 `adcode` 为空，告知无法定位并请用户提供城市名。
3. 调用 `get_weather_info(city_adcode=adcode)`（默认 `extensions=all`，含实况与预报）。
4. 用简洁中文汇报：当前实况 + 近几天预报要点。

## Planner 路由

- 天气
- 气温
- 温度
- 下雨
- 下雪
- 冷不冷
- 热不热
- weather
- forecast
- 天气预报

## 工具

| 工具 | 说明 |
|------|------|
| `lookup_ip_location` | （依赖 skill）IP 定位取 adcode |
| `search_district_tool` | （依赖 skill）行政区查询取 adcode |
| `get_weather_info` | 必填 `city_adcode`；默认 `extensions=all`。返回 JSON：`ok`, `lives`, `forecasts`。 |

## 回答要求

- 汇报温度、天气现象、风向风力、湿度及未来几天预报。
- 不得跳过定位步骤直接编造城市或天气。
