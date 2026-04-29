"""FastAPI ASGI entry: app wiring, CORS, rate-limit middleware, and startup lifespan."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.router import api
from app.config import settings
from app.errors import register_exception_handlers
from app.infrastructure.db.bootstrap import create_missing_tables
from app.limits import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure ORM tables exist when configured; release resources on shutdown."""

    await create_missing_tables()
    yield


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
if settings.app_env in ("dev", "development", "local", "test"):
    _cors["allow_origin_regex"] = r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$"
app.add_middleware(CORSMiddleware, **_cors)
app.include_router(api)
