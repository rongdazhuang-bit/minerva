# 概览页快捷应用入口设计说明

**日期**：2026-05-26  
**状态**：已实现（2026-05-26；2026-05-26 增补 token 用量曲线图）

---

## 11. 增补：智能体 Token 用量曲线（2026-05-26）

- **位置**：快捷应用入口单行下方
- **数据**：`GET /workspaces/{workspace_id}/agent/v2/overview-usage-daily-stats`
- **窗口**：近 7 个本地日历日（与 OCR 概览相同 TZ 规则）
- **Series**：`prompt_tokens`、`completion_tokens`、`details.cached_tokens`、`details.reasoning_tokens`
- **聚合源**：工作区内 `agent_run.usage_json`，按 `coalesce(finished_at, started_at)` 分桶  
**范围**：`minerva-ui` 概览页（`/app/overview`）主内容区 UI 改造

---

## 1. 目标与成功标准

- **替换内容**：删除现有 `OverviewPage` 中的欢迎区、演示 KPI 统计、最近活动列表，改为 6 个快捷应用入口卡片。
- **应用列表**：智能体、文档翻译、知识库、智能校审、规则库、文件 OCR。
- **视觉要求**：美观、整洁；统一卡片样式 + 每应用独立渐变图标背景。
- **布局要求**：无页面头部；卡片自内容区顶部对齐；均匀网格（等大卡片）。
- **卡片内容**：渐变图标 + 应用名称 + 一行简介。
- **成功标准**：
  - 登录默认页展示 6 张卡片，无多余头部文案；
  - 点击各卡片跳转至对应功能默认页；
  - Dark / Sunshine 双主题下样式正常；
  - 响应式在 lg / sm / xs 断点布局正确；
  - 键盘 Tab + Enter 可访问并跳转。

---

## 2. 设计决策（Brainstorming 结论）

| 维度 | 选择 |
|------|------|
| 布局 | A — 均匀卡片网格（3×2 / 2×3 / 1×6 响应式） |
| 页面头部 | C — 完全去掉，仅展示卡片 |
| 卡片信息 | B — 图标 + 名称 + 一行简介 |
| 配色 | C — 卡片本体统一，图标放在独立渐变圆角块中 |
| 垂直位置 | B — 顶部对齐，保留适当上内边距 |
| 实现方案 | 方案 1 — 就地改造 `OverviewPage.tsx` / `OverviewPage.css` |

---

## 3. 应用配置

| 应用 | 路由 | 图标（Ant Design） | 渐变色调 |
|------|------|-------------------|----------|
| 智能体 | `/app/agents/chat` | `RobotOutlined` | 蓝紫 |
| 文档翻译 | `/app/translate` | `TranslationOutlined` | 青绿 |
| 知识库 | `/app/knowledge-base` | `ReadOutlined` | 琥珀 |
| 智能校审 | `/app/smart-review` | `FileSearchOutlined` | 紫罗兰 |
| 规则库 | `/app/rules/overview` | `BookOutlined` | 天蓝 |
| 文件 OCR | `/app/file-ocr/overview` | `ScanOutlined` | 珊瑚橙 |

图标与路由与侧栏 `AppLayout` 菜单保持一致；有子菜单的应用跳转到各模块默认概览/主功能页。

---

## 4. 布局规格

```
┌─────────────────────────────────────────────┐
│  padding-top: 32px                          │
│                                             │
│  ┌──────┐  ┌──────┐  ┌──────┐              │
│  │ 卡片1 │  │ 卡片2 │  │ 卡片3 │   lg: 3 列   │
│  └──────┘  └──────┘  └──────┘              │
│  ┌──────┐  ┌──────┐  ┌──────┐              │
│  │ 卡片4 │  │ 卡片5 │  │ 卡片6 │              │
│  └──────┘  └──────┘  └──────┘              │
└─────────────────────────────────────────────┘
```

- **容器**：`.minerva-overview`，`max-width: 960px`，水平居中。
- **上内边距**：`padding-top: 32px`。
- **栅格**：Ant Design `Row` / `Col` + `gutter={[20, 20]}`。
- **响应式断点**：
  - `lg+`（≥992px）：`span={8}`，3 列 × 2 行；
  - `sm–md`（576–991px）：`span={12}`，2 列 × 3 行；
  - `xs`（<576px）：`span={24}`，1 列 × 6 行。
- **卡片等高**：同一行内卡片 `height: 100%`，内容区 flex 对齐。

---

## 5. 卡片结构与交互

### 5.1 结构

```
┌─────────────────────────┐
│  ┌────┐                 │
│  │渐变│  应用名称 (15px/600) │
│  │图标│  一行简介 (13px)     │
│  └────┘                 │
└─────────────────────────┘
```

- **渐变图标块**：48×48px，`border-radius: 12px`；图标 24px、白色；每应用独立 CSS 渐变（通过 modifier class 或 CSS 变量）。
- **卡片本体**：`background: var(--minerva-surface)`；`border: 1px solid var(--minerva-border)`；`border-radius: 12px`；内边距约 20px。
- **简介**：最多 2 行，`line-clamp: 2`；opacity 0.65（Dark）；Sunshine 下 `#64748b`。

### 5.2 交互

- 整卡可点击，使用 `<button type="button">` 或等效可聚焦元素，`onClick` 调用 `navigate(path)`。
- **Hover**：`translateY(-2px)` + 阴影加深（Dark: `rgba(0,0,0,0.22)`；Sunshine: `rgba(15,23,42,0.10)`）。
- **Focus-visible**：`outline` 使用 `--minerva-link`。
- **无障碍**：`aria-label` 含应用名称；图标 `aria-hidden`。

### 5.3 数据驱动

在 `OverviewPage.tsx` 内定义常量数组（或同文件内类型化配置），字段：`key`、`path`、`icon`、`gradientClass`、`titleKey`、`descKey`；`map` 渲染卡片，避免硬编码 6 份 JSX。

---

## 6. 样式与主题

沿用现有 CSS 变量与 `html.minerva-tone-sunshine` 双主题模式（参考 `OverviewPage.css`、`RulesOverviewPage.css`）。

**删除的样式**：原 hero、Statistic、activity list 相关 class（`__hero`、`__stats`、`__activity` 等）。

**新增样式**（示例命名）：

- `.minerva-overview__grid`
- `.minerva-overview__app-card`
- `.minerva-overview__app-icon` + `--agents` / `--translate` / … 渐变 modifier
- `.minerva-overview__app-name`
- `.minerva-overview__app-desc`

---

## 7. 国际化

### 7.1 新增 key（`zh-CN.json` / `en.json`）

| Key | 中文 | English |
|-----|------|---------|
| `overview.apps.agents` | 智能体 | Agents |
| `overview.apps.agentsDesc` | 与 AI 智能体对话协作 | Chat and collaborate with AI agents |
| `overview.apps.translate` | 文档翻译 | Document translation |
| `overview.apps.translateDesc` | 多语言文档智能翻译 | Intelligent multilingual document translation |
| `overview.apps.knowledgeBase` | 知识库 | Knowledge base |
| `overview.apps.knowledgeBaseDesc` | 集中管理与检索知识文档 | Manage and search knowledge documents |
| `overview.apps.smartReview` | 智能校审 | Smart review |
| `overview.apps.smartReviewDesc` | 基于规则的文档智能校审 | Rule-based intelligent document review |
| `overview.apps.rules` | 规则库 | Rules |
| `overview.apps.rulesDesc` | 查看与管理校审规则 | View and manage review rules |
| `overview.apps.fileOcr` | 文件 OCR | File OCR |
| `overview.apps.fileOcrDesc` | 批量文档 OCR 识别与任务管理 | Batch document OCR and task management |

### 7.2 删除 key（仅 `OverviewPage` 使用，改造后移除）

- `home.title`、`home.subtitle`
- `overview.stat.*`、`overview.refreshedAt`、`overview.recentTitle`、`overview.activity*`

---

## 8. 文件变更范围

| 文件 | 操作 |
|------|------|
| `minerva-ui/src/features/workspace/OverviewPage.tsx` | 重写为快捷入口网格 |
| `minerva-ui/src/features/workspace/OverviewPage.css` | 替换为新卡片样式 |
| `minerva-ui/src/i18n/locales/zh-CN.json` | 新增 / 删除 i18n key |
| `minerva-ui/src/i18n/locales/en.json` | 新增 / 删除 i18n key |

**不变**：路由（仍为 `/app/overview`）、`AppLayout` 侧栏、后端 API。

---

## 9. 测试与验收

### 9.1 手动验收清单

1. 登录后默认进入概览，见 6 张卡片、无头部文案。
2. 依次点击 6 张卡片，路由跳转正确。
3. 切换 Dark / Sunshine 主题，卡片与渐变正常。
4. 浏览器宽度 1440 → 768 → 375px，列数按规格变化。
5. 键盘 Tab 聚焦卡片，Enter 触发跳转。

### 9.2 自动化测试

不新增（纯静态 UI，手动验收即可）。

---

## 10. 范围外

- 用户自定义排序 / 收藏 / 隐藏应用；
- 基于权限的动态入口过滤（菜单配置 `MenuConfigPage` 仍为占位）；
- 卡片上展示实时 KPI 或统计数据；
- 抽离通用 `QuickLaunchGrid` 组件（当前仅一处使用，YAGNI）。
