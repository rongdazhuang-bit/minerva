# ip_location

通过高德 IP 定位 API 查询 IP 所在省市与 adcode（禁止编造位置）。

## 何时使用

**Planner 必选本 skill（`skill_id=ip_location`）**：用户询问当前位置、IP 所在城市/省份、我在哪等问题。

**子 Agent 执行**：须调用 `lookup_ip_location`；`ip` 参数仅在用户明确给出 IP 时填写，否则留空以定位请求方 IP。

## Planner 路由

- 我在哪
- 我的位置
- 当前 IP
- IP 定位
- ip location
- where am i
- 我在什么地方

## 工具

| 工具 | 说明 |
|------|------|
| `lookup_ip_location` | 可选参数 `ip`。返回 JSON：`ok`, `province`, `city`, `adcode`, `rectangle`。 |

## 回答要求

- `adcode` 为空（局域网/国外 IP）时，告知无法自动定位，请用户提供城市名。
- 用简洁中文回答省市信息。
