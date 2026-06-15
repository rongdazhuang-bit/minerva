# 高德 IP / 行政区 / 天气 Agent Skills 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Minerva Agent 新增 `ip_location`、`district`、`weather` 三个运行时 skill，经共享 `amap_client` 调用高德 Web 服务 API；`weather` 激活时自动加载依赖工具。

**Architecture:** `amap_client.py` 封装三 API 的 httpx 异步调用与统一 JSON 契约；各 skill 的 `tools.py` 各注册一个 LangChain tool；`skill_loader` 维护 `weather → (ip_location, district)` 依赖表并按 tool.name 去重合并。

**Tech Stack:** Python 3.11+, httpx, pydantic-settings, langchain_core.tools, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-06-15-amap-location-weather-skills-design.md`

---

## 文件清单

| 操作 | 路径 | 职责 |
|------|------|------|
| Create | `backend/app/agent/infrastructure/amap_client.py` | 高德 HTTP 客户端 |
| Modify | `backend/app/config.py` | `amap_web_service_key` |
| Modify | `backend/.env.example` | 环境变量占位 |
| Modify | `backend/.env.dev` | dev 环境变量占位 |
| Modify | `backend/app/agent/infrastructure/skill_loader.py` | 依赖自动加载 |
| Create | `backend/app/agent/skills/ip_location/SKILL.md` | IP 定位 skill 说明 |
| Create | `backend/app/agent/skills/ip_location/tools.py` | `lookup_ip_location` |
| Create | `backend/app/agent/skills/district/SKILL.md` | 行政区 skill 说明 |
| Create | `backend/app/agent/skills/district/tools.py` | `search_district` |
| Create | `backend/app/agent/skills/weather/SKILL.md` | 天气 skill 说明 |
| Create | `backend/app/agent/skills/weather/tools.py` | `get_weather` |
| Modify | `backend/app/agent/skills/INDEX.md` | 注册三 skill |
| Create | `backend/tests/test_amap_client.py` | 客户端单测 |
| Create | `backend/tests/test_amap_skills.py` | skill 工具与依赖单测 |

---

### Task 1: Settings 与环境变量

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/.env.dev`

- [ ] **Step 1:** 在 `Settings` 末尾（`dataset_weaviate_api_key` 之后）添加 `amap_web_service_key` 字段
- [ ] **Step 2:** 在两份 env 文件追加 `AMAP_WEB_SERVICE_KEY=`（空值，注释说明用途）

---

### Task 2: amap_client（TDD）

**Files:**
- Create: `backend/tests/test_amap_client.py`
- Create: `backend/app/agent/infrastructure/amap_client.py`

- [ ] **Step 1:** 编写失败测试（Key 缺失、IP 成功、district 成功、weather 成功、API 业务失败）
- [ ] **Step 2:** 运行 `pytest backend/tests/test_amap_client.py -v` 确认 FAIL
- [ ] **Step 3:** 实现 `lookup_ip` / `search_district` / `get_weather`
- [ ] **Step 4:** 运行测试确认 PASS

---

### Task 3: 三个 Skill 包

**Files:**
- Create: `backend/app/agent/skills/ip_location/`
- Create: `backend/app/agent/skills/district/`
- Create: `backend/app/agent/skills/weather/`

- [ ] **Step 1:** 各 skill 编写 `SKILL.md`（含 Planner 路由与 weather 决策链）
- [ ] **Step 2:** 各 `tools.py` 实现 `register_tools` 返回单 tool
- [ ] **Step 3:** 更新 `INDEX.md`

---

### Task 4: skill_loader 依赖加载

**Files:**
- Modify: `backend/app/agent/infrastructure/skill_loader.py`
- Create: `backend/tests/test_amap_skills.py`

- [ ] **Step 1:** 测试 weather 加载后含 3 个 tool 名
- [ ] **Step 2:** 实现 `_SKILL_TOOL_DEPENDENCIES` 与去重合并逻辑
- [ ] **Step 3:** 运行 `pytest backend/tests/test_amap_skills.py backend/tests/test_amap_client.py -v`

---

### Task 5: Spec 回填

**Files:**
- Modify: `docs/superpowers/specs/2026-06-15-amap-location-weather-skills-design.md`

- [ ] **Step 1:** 更新状态为「已实现」并填写实现对照表
