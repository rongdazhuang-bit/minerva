# 概览页快捷应用入口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `/app/overview` 主内容区替换为 6 个快捷应用入口卡片（均匀网格、渐变图标、无头部），点击跳转至各功能默认页。

**Architecture:** 在现有 `OverviewPage.tsx` 内以配置数组驱动渲染；样式集中在 `OverviewPage.css`，沿用 `--minerva-*` token 与 `html.minerva-tone-sunshine` 双主题；i18n 新增应用名称/简介 key 并删除旧演示文案 key。不新增路由、后端或通用组件。

**Tech Stack:** React 18, TypeScript, Ant Design 6, `@ant-design/icons`, react-i18next, react-router-dom, Vite。

**设计依据:** `docs/superpowers/specs/2026-05-26-overview-quick-launch-design.md`

---

## 文件结构（将修改）

| 路径 | 职责 |
|------|------|
| `frontend/src/i18n/locales/zh-CN.json` | 新增 `overview.apps.*`；删除旧 `overview.stat.*` / `home.*` 等 |
| `frontend/src/i18n/locales/en.json` | 同上（英文） |
| `frontend/src/features/workspace/OverviewPage.css` | 快捷入口网格、卡片、渐变图标、hover/focus、双主题 |
| `frontend/src/features/workspace/OverviewPage.tsx` | 配置驱动的 6 卡片网格与导航 |

**不变:** `frontend/src/app/router.tsx`（路由仍为 `overview` → `OverviewPage`）。

---

## Task 1: 国际化文案

**Files:**

- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: 在 zh-CN.json 替换 overview / home 区块**

找到现有键（约 636–649 行）：

```json
  "overview.stat.todayReview": "今日校审",
  ...
  "home.subtitle": "您已成功进入工作区。可在此继续扩展功能模块。",
```

**整段替换为：**

```json
  "overview.apps.agents": "智能体",
  "overview.apps.agentsDesc": "与 AI 智能体对话协作",
  "overview.apps.translate": "文档翻译",
  "overview.apps.translateDesc": "多语言文档智能翻译",
  "overview.apps.knowledgeBase": "知识库",
  "overview.apps.knowledgeBaseDesc": "集中管理与检索知识文档",
  "overview.apps.smartReview": "智能校审",
  "overview.apps.smartReviewDesc": "基于规则的文档智能校审",
  "overview.apps.rules": "规则库",
  "overview.apps.rulesDesc": "查看与管理校审规则",
  "overview.apps.fileOcr": "文件 OCR",
  "overview.apps.fileOcrDesc": "批量文档 OCR 识别与任务管理",
```

- [ ] **Step 2: 在 en.json 做同样替换**

```json
  "overview.apps.agents": "Agents",
  "overview.apps.agentsDesc": "Chat and collaborate with AI agents",
  "overview.apps.translate": "Document translation",
  "overview.apps.translateDesc": "Intelligent multilingual document translation",
  "overview.apps.knowledgeBase": "Knowledge base",
  "overview.apps.knowledgeBaseDesc": "Manage and search knowledge documents",
  "overview.apps.smartReview": "Smart review",
  "overview.apps.smartReviewDesc": "Rule-based intelligent document review",
  "overview.apps.rules": "Rules",
  "overview.apps.rulesDesc": "View and manage review rules",
  "overview.apps.fileOcr": "File OCR",
  "overview.apps.fileOcrDesc": "Batch document OCR and task management",
```

- [ ] **Step 3: 验证 JSON 合法**

Run:

```bash
cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/zh-CN.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/en.json','utf8')); console.log('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN.json frontend/src/i18n/locales/en.json
git commit -m "feat(ui): i18n keys for overview quick launch apps"
```

---

## Task 2: 样式 — OverviewPage.css

**Files:**

- Modify: `frontend/src/features/workspace/OverviewPage.css`（整文件替换）

- [ ] **Step 1: 写入完整 CSS**

将 `OverviewPage.css` **全部内容**替换为：

```css
/* 概览 — 快捷应用入口网格 */

.minerva-overview {
  max-width: 960px;
  margin: 0 auto;
  padding-top: 32px;
}

.minerva-overview__grid {
  width: 100%;
}

.minerva-overview__app-card {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  width: 100%;
  height: 100%;
  min-height: 108px;
  padding: 20px;
  margin: 0;
  text-align: start;
  cursor: pointer;
  color: inherit;
  font: inherit;
  background: var(--minerva-surface, #1a2836);
  border: 1px solid var(--minerva-border, #2a3f58);
  border-radius: 12px;
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.2);
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease;
}

.minerva-overview__app-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.22);
}

.minerva-overview__app-card:focus-visible {
  outline: 2px solid var(--minerva-link, #38bdf8);
  outline-offset: 2px;
}

.minerva-overview__app-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 12px;
  font-size: 24px;
  color: #fff;
}

.minerva-overview__app-icon--agents {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
}

.minerva-overview__app-icon--translate {
  background: linear-gradient(135deg, #14b8a6 0%, #22c55e 100%);
}

.minerva-overview__app-icon--knowledge-base {
  background: linear-gradient(135deg, #f59e0b 0%, #f97316 100%);
}

.minerva-overview__app-icon--smart-review {
  background: linear-gradient(135deg, #a855f7 0%, #ec4899 100%);
}

.minerva-overview__app-icon--rules {
  background: linear-gradient(135deg, #0ea5e9 0%, #3b82f6 100%);
}

.minerva-overview__app-icon--file-ocr {
  background: linear-gradient(135deg, #f97316 0%, #ef4444 100%);
}

.minerva-overview__app-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.minerva-overview__app-name {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--minerva-ink, #e8f0f8);
}

.minerva-overview__app-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
  color: var(--minerva-ink, #e8f0f8);
  opacity: 0.65;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

html.minerva-tone-sunshine .minerva-overview__app-card {
  background: var(--minerva-surface, #fff);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}

html.minerva-tone-sunshine .minerva-overview__app-card:hover {
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.1);
}

html.minerva-tone-sunshine .minerva-overview__app-name {
  color: var(--minerva-ink, #0f172a);
}

html.minerva-tone-sunshine .minerva-overview__app-desc {
  color: #64748b;
  opacity: 1;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/workspace/OverviewPage.css
git commit -m "feat(ui): overview quick launch card styles"
```

---

## Task 3: 组件 — OverviewPage.tsx

**Files:**

- Modify: `frontend/src/features/workspace/OverviewPage.tsx`（整文件替换）

- [ ] **Step 1: 写入完整组件**

将 `OverviewPage.tsx` **全部内容**替换为：

```tsx
import {
  BookOutlined,
  FileSearchOutlined,
  ReadOutlined,
  RobotOutlined,
  ScanOutlined,
  TranslationOutlined,
} from '@ant-design/icons'
import { Col, Row } from 'antd'
import type { ComponentType, ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import './OverviewPage.css'

/** 快捷入口单项：路由、图标、渐变 modifier、i18n 键。 */
type OverviewAppItem = {
  key: string
  path: string
  icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean }>
  iconModifier:
    | 'agents'
    | 'translate'
    | 'knowledge-base'
    | 'smart-review'
    | 'rules'
    | 'file-ocr'
  titleKey: string
  descKey: string
}

/** 概览页 6 个快捷应用入口配置（顺序即展示顺序）。 */
const OVERVIEW_APPS: OverviewAppItem[] = [
  {
    key: 'agents',
    path: '/app/agents/chat',
    icon: RobotOutlined,
    iconModifier: 'agents',
    titleKey: 'overview.apps.agents',
    descKey: 'overview.apps.agentsDesc',
  },
  {
    key: 'translate',
    path: '/app/translate',
    icon: TranslationOutlined,
    iconModifier: 'translate',
    titleKey: 'overview.apps.translate',
    descKey: 'overview.apps.translateDesc',
  },
  {
    key: 'knowledge-base',
    path: '/app/knowledge-base',
    icon: ReadOutlined,
    iconModifier: 'knowledge-base',
    titleKey: 'overview.apps.knowledgeBase',
    descKey: 'overview.apps.knowledgeBaseDesc',
  },
  {
    key: 'smart-review',
    path: '/app/smart-review',
    icon: FileSearchOutlined,
    iconModifier: 'smart-review',
    titleKey: 'overview.apps.smartReview',
    descKey: 'overview.apps.smartReviewDesc',
  },
  {
    key: 'rules',
    path: '/app/rules/overview',
    icon: BookOutlined,
    iconModifier: 'rules',
    titleKey: 'overview.apps.rules',
    descKey: 'overview.apps.rulesDesc',
  },
  {
    key: 'file-ocr',
    path: '/app/file-ocr/overview',
    icon: ScanOutlined,
    iconModifier: 'file-ocr',
    titleKey: 'overview.apps.fileOcr',
    descKey: 'overview.apps.fileOcrDesc',
  },
]

type OverviewAppCardProps = {
  item: OverviewAppItem
  title: string
  description: string
  onOpen: (path: string) => void
}

/** 单个快捷应用入口卡片（整卡可点击）。 */
function OverviewAppCard({ item, title, description, onOpen }: OverviewAppCardProps) {
  const Icon = item.icon

  return (
    <button
      type="button"
      className="minerva-overview__app-card"
      aria-label={title}
      onClick={() => onOpen(item.path)}
    >
      <span
        className={`minerva-overview__app-icon minerva-overview__app-icon--${item.iconModifier}`}
        aria-hidden
      >
        <Icon />
      </span>
      <span className="minerva-overview__app-body">
        <span className="minerva-overview__app-name">{title}</span>
        <span className="minerva-overview__app-desc">{description}</span>
      </span>
    </button>
  )
}

/** 工作区概览页：快捷应用入口网格。 */
export function OverviewPage(): ReactNode {
  const { t } = useTranslation()
  const navigate = useNavigate()

  return (
    <div className="minerva-overview">
      <Row gutter={[20, 20]} className="minerva-overview__grid">
        {OVERVIEW_APPS.map((item) => (
          <Col key={item.key} xs={24} sm={12} lg={8}>
            <OverviewAppCard
              item={item}
              title={t(item.titleKey)}
              description={t(item.descKey)}
              onOpen={(path) => void navigate(path)}
            />
          </Col>
        ))}
      </Row>
    </div>
  )
}
```

- [ ] **Step 2: TypeScript 编译检查**

Run:

```bash
cd frontend && npm run build
```

Expected: 命令成功退出（`tsc -b && vite build` 无 error）。

- [ ] **Step 3: ESLint**

Run:

```bash
cd frontend && npm run lint
```

Expected: 无 error（允许既有仓库 warn，但本文件不得新增 error）。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/workspace/OverviewPage.tsx
git commit -m "feat(ui): replace overview page with quick launch app grid"
```

---

## Task 4: 手动验收

**Files:** 无代码变更；浏览器验证。

- [ ] **Step 1: 启动开发服务器**

Run:

```bash
cd frontend && npm run dev
```

在浏览器打开应用并登录，确认默认进入 `/app/overview`。

- [ ] **Step 2: 布局与内容**

确认：

- 无欢迎标题 / KPI / 最近动态；
- 可见 6 张等大卡片，顶部有约 32px 留白；
- 每张卡片含渐变图标、名称、一行简介。

- [ ] **Step 3: 导航**

依次点击 6 张卡片，确认路由分别为：

| 卡片 | 期望路径 |
|------|----------|
| 智能体 | `/app/agents/chat` |
| 文档翻译 | `/app/translate` |
| 知识库 | `/app/knowledge-base` |
| 智能校审 | `/app/smart-review` |
| 规则库 | `/app/rules/overview` |
| 文件 OCR | `/app/file-ocr/overview` |

- [ ] **Step 4: 主题与响应式**

- 在 Header 切换 Dark / Sunshine，卡片背景、文字、hover 阴影正常；
- 将视口调至约 375px（1 列）、768px（2 列）、≥992px（3 列）。

- [ ] **Step 5: 键盘无障碍**

Tab 聚焦卡片，Enter 触发跳转；聚焦环可见（`focus-visible` outline）。

- [ ] **Step 6: 更新 spec 状态（可选）**

若实现与设计一致，将 `docs/superpowers/specs/2026-05-26-overview-quick-launch-design.md` 头部 **状态** 改为「已实现」。

---

## Spec 覆盖自检

| Spec 要求 | 对应 Task |
|-----------|-----------|
| 删除 hero / KPI / 活动列表 | Task 3 |
| 6 应用 + 路由 | Task 3 `OVERVIEW_APPS` |
| 均匀网格 + 响应式 3/2/1 列 | Task 3 `Col` + Task 2 CSS |
| 无头部 | Task 3（无 hero JSX） |
| 图标 + 名称 + 简介 | Task 3 `OverviewAppCard` |
| 渐变图标 + 统一卡片 | Task 2 渐变 modifier |
| 顶部对齐 padding-top 32px | Task 2 `.minerva-overview` |
| hover / focus-visible | Task 2 |
| i18n 新增/删除 | Task 1 |
| 双主题 | Task 2 sunshine 块 |
| 手动验收清单 | Task 4 |

**范围外项**（spec §10）：未纳入本计划 — 符合预期。

---

## 执行选项

Plan 已保存至 `docs/superpowers/plans/2026-05-26-overview-quick-launch.md`。

**1. Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，任务间 review，迭代快

**2. Inline Execution** — 在本会话内按 Task 顺序直接改代码并验收

你想用哪种方式执行？
