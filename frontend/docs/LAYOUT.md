# 布局与滚动约定

## 已登录应用壳（`html.minerva-app-shell`）

- 整页（`html` / `body` / `#root`）固定视口高度，**不产生整页滚动**。
- 由 `.minerva-spa-wrapper` 与 `.minerva-route-surface` 形成纵向 flex 链，子项 `min-height: 0` 以正确参与收缩。
- 顶栏、侧栏、导航 Tag 栏固定；右侧主体在壳层内排布。
- 主内容区上方为**多 Tag 导航栏**（侧栏打开的页面标签；同一菜单叶子只保留一个 Tag）。详见 `docs/superpowers/specs/2026-08-20-app-nav-tags-design.md`。

### 右侧主体区（硬性，与 `.cursor/rules/frontend-main-layout.mdc` 一致）

1. **圆角**：表格、卡片及同类容器 **4px**（`--minerva-page-frame-radius` / Ant Design `token.borderRadius`）；胶囊 / 圆形 / Tag 翼角除外。
2. **边距与滚动**：`.minerva-app-main-scroll` 距四周 **3px**；**默认整体不滚动**（`overflow: hidden`）。长内容在页内滚动。禁止 `scrollbar-gutter: stable`。
3. **外框**：`Outlet` 外包 `.minerva-app-main-frame`（4px 圆角 + 边框 + surface），包住页面全部组件。
   - 概览/占位页根节点加 **`minerva-page-fill`**（铺满外框、内边距、页内滚动）。
   - 全页布局用的 Ant `Card` 加 **`minerva-page-shell-card`**，去掉第二层描边/阴影（勿再叠全幅外壳 Card）。
   - **例外**：`/app/agents/chat` 不套外框。

## 侧栏宽度与折叠

- 左侧导航宽度可通过**右侧拖条**调整，**最大宽度**为中间内容行（顶栏下主行）宽度的 **20%**，**最窄 120px**；拖条支持鼠标与触摸。
- 展开宽度持久化在 `localStorage` 键 `minerva_sider_width`。
- 侧栏底部按钮可**折叠为仅图标**（宽 64px）；折叠态持久化在 `minerva_sider_collapsed`（`1` / `0`）。折叠时隐藏拖条；带子级的菜单项**点击图标**后以浮层（挂到 `document.body`）展开，可选中子项与多级子菜单。

## 对比：认证全屏（`html.minerva-auth-page`）

- 登录/注册页使用独立的全屏与背景，与上述应用壳的滚动策略分开处理；详见 `AuthPage.css`。
