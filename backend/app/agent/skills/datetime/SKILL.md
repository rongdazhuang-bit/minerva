# datetime

获取服务器当前日期与时间（通过工具 `get_system_datetime`，禁止编造）。

## 何时使用

**Planner 必选本 skill（`skill_id=datetime`）**：用户要的是「此刻」真实日期、时刻或星期，而不是概念解释或历史日期推算。此类问题禁止使用 `general`（general 无时间工具，会错误回答「无法查询」）。

**子 Agent 执行**：进入本 skill 后必须先调用 `get_system_datetime`（向用户报告本地时间时用 `timezone=LOCAL`），再根据返回的 `iso` 用中文简洁作答；不得声称无法获取实时时间。

## Planner 路由

- 现在几点
- 几点了
- 几时了
- 当前时间
- 现在时间
- 今天几号
- 今日几号
- 什么日期
- 几月几号
- 今天星期几
- 星期几
- 周几
- what time is it
- what's the date

## 工具

| 工具 | 说明 |
|------|------|
| `get_system_datetime` | 参数 `timezone`：`UTC` 或 `LOCAL`（默认 `UTC`）。返回 JSON：`ok`, `iso`, `timezone`, `unix`。 |

## 回答要求

根据工具返回的 `iso` 用简洁中文回答用户问题（可含日期、时刻、星期）。
