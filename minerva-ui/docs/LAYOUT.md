# 布局与滚动约定

## 已登录应用壳（`html.minerva-app-shell`）

- 整页（`html` / `body` / `#root`）固定视口高度，**不产生整页滚动**。
- 由 `.minerva-spa-wrapper` 与 `.minerva-route-surface` 形成纵向 flex 链，子项 `min-height: 0` 以正确参与收缩。
- **仅主内容区域**在内部滚动；面包屑、顶栏、侧栏等不随长内容整页被拖走。

## 侧栏宽度与折叠

- 左侧导航宽度可通过**右侧拖条**调整，**最大宽度**为中间内容行（顶栏下主行）宽度的 **20%**，**最窄 120px**；拖条支持鼠标与触摸。
- 展开宽度持久化在 `localStorage` 键 `minerva_sider_width`。
- 侧栏底部按钮可**折叠为仅图标**（宽 64px）；折叠态持久化在 `minerva_sider_collapsed`（`1` / `0`）。折叠时隐藏拖条；带子级的菜单项**点击图标**后以浮层（挂到 `document.body`）展开，可选中子项与多级子菜单。

## 对比：认证全屏（`html.minerva-auth-page`）

- 登录/注册页使用独立的全屏与背景，与上述应用壳的滚动策略分开处理；详见 `AuthPage.css`。
