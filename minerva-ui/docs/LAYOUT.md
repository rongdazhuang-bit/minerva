# 布局与滚动约定

## 已登录应用壳（`html.minerva-app-shell`）

- 整页（`html` / `body` / `#root`）固定视口高度，**不产生整页滚动**。
- 由 `.minerva-spa-wrapper` 与 `.minerva-route-surface` 形成纵向 flex 链，子项 `min-height: 0` 以正确参与收缩。
- **仅主内容区域**在内部滚动；面包屑、顶栏、侧栏等不随长内容整页被拖走。

## 侧栏宽度

- 左侧导航宽度可通过拖条调整，**最大宽度**为中间内容行（顶栏下主行）宽度的 **20%**，**最窄 120px**。
- 当前值持久化在 `localStorage` 键 `minerva_sider_width`。

## 对比：认证全屏（`html.minerva-auth-page`）

- 登录/注册页使用独立的全屏与背景，与上述应用壳的滚动策略分开处理；详见 `AuthPage.css`。
