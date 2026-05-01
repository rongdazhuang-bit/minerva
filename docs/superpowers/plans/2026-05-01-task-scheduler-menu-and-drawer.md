# Task Scheduler Menu & Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move “Task scheduler” under File storage in the Settings menu, and change “Create task scheduler” from a modal to a right-side drawer.

**Architecture:** Keep existing routes (`/app/settings/celery`) and data flow intact; adjust only navigation order, labels, and the container component for the create/edit form (Modal → Drawer).

**Tech Stack:** React, TypeScript, Ant Design, react-router, react-i18next.

---

### Task 1: Move menu item under File storage

**Files:**
- Modify: `minerva-ui/src/app/layout/AppLayout.tsx`

- [ ] **Step 1: Update menu item order**
  - In Settings submenu items, move the “celery” item (`key: 'settings-celery'`) to be directly after “file-storage”.

- [ ] **Step 2: Smoke-check navigation**
  - Run the dev server and confirm the Settings submenu order visually.

---

### Task 2: Rename labels to “任务调度 / Create task scheduler”

**Files:**
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`
- Modify: `minerva-ui/src/i18n/locales/en.json`

- [ ] **Step 1: Update i18n labels**
  - Change `settings.celery` to “任务调度” (en: “Task scheduler”).
  - Change action add label from “新增 Celery 任务” to “创建任务调度” (en: “Create task scheduler”).
  - Update create/edit titles accordingly.

- [ ] **Step 2: Verify UI text**
  - Navigate to the page and confirm the sidebar and create button use the new labels.

---

### Task 3: Replace create/edit modal with right-side drawer

**Files:**
- Modify: `minerva-ui/src/features/settings/celery/CeleryPage.tsx`
- Modify: `minerva-ui/src/features/settings/celery/CeleryFormModal.tsx` (or equivalent form container)

- [ ] **Step 1: Write a failing UI test (optional if project has no front-end test harness)**
  - If `vitest`/`react-testing-library` exists, add a test asserting the create container is a Drawer and not a Modal.
  - Otherwise, skip automated tests and verify via manual run.

- [ ] **Step 2: Implement Drawer container**
  - Replace `Modal` usage with `Drawer` (`placement="right"`, `width` ~ 520–720).
  - Keep form component and submission logic unchanged.
  - Ensure close behavior works via Drawer close button and Cancel action.

- [ ] **Step 3: Run typecheck/build**
  - Run: `pnpm -C minerva-ui typecheck` (or `pnpm -C minerva-ui build` if no typecheck script).
  - Expected: No TypeScript errors.

---

### Task 4: Breadcrumb coverage for `/app/settings/celery`

**Files:**
- Modify: `minerva-ui/src/app/layout/AppBreadcrumb.tsx`

- [ ] **Step 1: Add leaf title**
  - Extend `settingsLeafTitle()` to return `t('settings.celery')` for `/app/settings/celery`.

- [ ] **Step 2: Verify breadcrumb**
  - Navigate to the page and confirm breadcrumb shows: Home / System settings / 任务调度.

