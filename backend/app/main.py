"""FastAPI ASGI entry: app wiring, CORS, rate-limit middleware, and startup lifespan."""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager

# psycopg 异步池在 Windows 默认 ProactorEventLoop 下无法建连；须在事件循环创建前切换。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.core.api.router import api
from app.core.api.routers import health, probe
from app.core.logging_config import configure_logging
from app.core.logging_middleware import HttpLoggingMiddleware
from app.errors import register_exception_handlers
from app.agent.infrastructure.langgraph_checkpointer import close_langgraph_checkpointer
from app.core.infrastructure.db.bootstrap import create_missing_tables
from app.core.infrastructure.db.session import async_session_factory
from app.mcp.runtime.registry import mcp_registry
from app.mcp.runtime.server_router import mount_mcp_server_routes
from app.mcp.runtime.server_runtime import mcp_outbound_runtime
from app.sys.menu.service.menu_seed import bootstrap_sys_menu_seed
from app.limits import limiter

configure_logging(process_type="api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure ORM tables exist when configured; release resources on shutdown."""

    await create_missing_tables()
    await bootstrap_sys_menu_seed()
    if settings.mcp_client_enabled or settings.mcp_server_enabled:
        async with async_session_factory() as session:
            await mcp_registry.warm_from_db(session)
    async with mcp_outbound_runtime.lifespan():
        if settings.mcp_server_enabled:
            mount_mcp_server_routes(app, mcp_registry)
        # LangGraph checkpoint 在首次 Agent 运行时懒加载，避免启动阻塞 HTTP（尤其 Windows 上池初始化较慢）。
        yield
    await close_langgraph_checkpointer()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
register_exception_handlers(app)
# Browser-facing CORS: localhost dev URLs plus regex matching when APP_ENV is dev-like.
_cors: dict = {
    "allow_origins": [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
# Dev: localhost/127.0.0.1 plus RFC1918 LAN hosts (e.g. http://192.168.x.x:5173).
_DEV_CORS_ORIGIN_REGEX = (
    r"^https?://("
    r"127\.0\.0\.1|localhost|"
    r"10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}"
    r")(:\d+)?$"
)
if settings.app_env in ("dev", "development", "local", "test"):
    _cors["allow_origin_regex"] = _DEV_CORS_ORIGIN_REGEX
app.add_middleware(HttpLoggingMiddleware)
app.add_middleware(CORSMiddleware, **_cors)
app.include_router(health.router)
app.include_router(probe.router)
app.include_router(api, prefix="/api")
