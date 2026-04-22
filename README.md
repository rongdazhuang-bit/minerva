# minerva

#### 介绍
文档智能校审

#### 软件架构
软件架构说明


#### 安装教程

1.  **依赖**：安装 Docker、Python 3.11+、Node 20+；仓库根目录 `docker compose up -d` 启动 Postgres 与 Redis。
2.  **后端**：`cd backend`；复制 `../.env.example` 为 `backend/.env` 并按需改库连接；`pip install -e ".[dev]"`；`alembic upgrade head`；`uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`。
3.  **前端**：`cd minerva-ui`；`copy .env.example .env`（将 `VITE_API_BASE_URL` 指向 `http://127.0.0.1:8000`）；`npm install`；`npm run dev`（默认 `http://127.0.0.1:5173`）。在浏览器中注册账号后即可使用规则、设计器、执行等页面。API 与 CORS 已按该地址配置。

#### 使用说明

1.  登录/注册 使用后端 `/auth/*` 接口；工作空间 `workspace_id` 来自 access token 中的 `wid`。
2.  规则列表与设计器 调用 `GET/POST /workspaces/{id}/rules` 等接口；**运行** 需规则已**发布**（`current_published_version_id` 非空）；执行记录来自 `/workspaces/{id}/executions`。
3.  可选：在 `backend` 下另开终端使用 `arq app.worker.arq.WorkerSettings` 处理执行步进与 Redis 锁（需本机可连 Redis）。

#### 参与贡献

1.  Fork 本仓库
2.  新建 Feat_xxx 分支
3.  提交代码
4.  新建 Pull Request


#### 特技

1.  使用 Readme\_XXX.md 来支持不同的语言，例如 Readme\_en.md, Readme\_zh.md
2.  Gitee 官方博客 [blog.gitee.com](https://blog.gitee.com)
3.  你可以 [https://gitee.com/explore](https://gitee.com/explore) 这个地址来了解 Gitee 上的优秀开源项目
4.  [GVP](https://gitee.com/gvp) 全称是 Gitee 最有价值开源项目，是综合评定出的优秀开源项目
5.  Gitee 官方提供的使用手册 [https://gitee.com/help](https://gitee.com/help)
6.  Gitee 封面人物是一档用来展示 Gitee 会员风采的栏目 [https://gitee.com/gitee-stars/](https://gitee.com/gitee-stars/)
