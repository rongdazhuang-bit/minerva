# 应用壳多 Tag 导航设计说明

**日期**：2026-08-20  
**状态**：已实现  
**范围**：已登录应用壳将原面包屑栏替换为可多开的导航 Tag 栏；侧栏点击新建或激活 Tag；同一菜单叶子只保留一个 Tag；支持关闭与切换跳转。不做页面 keep-alive。

**关系**：替换 `frontend/src/app/layout/AppBreadcrumb.tsx` 在壳层的展示职责；滚动与壳布局约定见 `frontend/docs/LAYOUT.md`。

---

## 1. 目标与成功标准

### 1.1 目标

- 主内容区上方固定 Tag 栏（不随主内容滚动）。
- 侧栏菜单点击 → `navigate(path)`；若该菜单叶子已有 Tag 则激活，否则新建。
- Tag 身份按**菜单叶子 path**合并（最长路径前缀命中）；详情子路由仍激活对应菜单 Tag。
- `/app/overview` 为固定首个、不可关闭 Tag；Tag 栏始终显示。
- 关闭当前 Tag 时跳到右侧邻近，否则左侧；仅剩概览时回概览。

### 1.2 成功标准

- 侧栏两次点击同一叶子菜单，只存在一个对应 Tag 且为激活态。
- 从知识库列表进入详情 URL，仍高亮知识库菜单对应 Tag，不另开。
- 关闭非概览 Tag 后列表与路由一致；概览 Tag 无关闭按钮。
- 切换 Tag 仅路由跳转，页面随路由挂载/卸载。

### 1.3 非目标（本期）

- 多页面 keep-alive / 缓存滚动位置
- Tag 列表持久化到 localStorage
- 右键菜单（关闭其它 / 关闭右侧等）

---

## 2. 行为说明

| 动作 | 行为 |
|------|------|
| 侧栏叶子点击 | `navigate` 到菜单 path；pathname 同步驱动开 Tag / 激活 |
| pathname 变化 | `findBestMenuHit`；有命中则 key=菜单规范化 path；无命中则 key=规范化 pathname |
| 点击 Tag | `navigate` 到该 Tag 记录的 path（菜单叶子 path，或无菜单时的 pathname） |
| 关闭 Tag | 移除；若关闭的是当前页则邻页跳转 |

标题：优先菜单 `i18n_key`，否则 `menu_name`；无菜单命中时用 fallback 叶子标题（原面包屑叶子逻辑）。

---

## 3. 实现对照（以代码为准，2026-08-20）

| Spec 条目 | 当前代码位置 | 备注 |
|-----------|--------------|------|
| Tag 栏 UI | `frontend/src/app/layout/AppNavTags.tsx`、`appNavTags.css` | 替换原 `AppBreadcrumb` |
| 开/激活/关 | `frontend/src/app/layout/useAppNavTags.ts` | 会话内内存 |
| 菜单命中 + 标题 | `frontend/src/app/layout/resolveNavTag.ts`、`menuNavMatch.ts` | 导出 `findBestMenuHit` |
| 壳接入 | `frontend/src/app/layout/AppLayout.tsx` | 始终渲染 Tag 栏 |
| 布局文档 | `frontend/docs/LAYOUT.md` | 面包屑 → Tag 栏 |
| i18n | `frontend/src/i18n/locales/zh-CN.json`、`en.json` | `layout.navTags.*` |
