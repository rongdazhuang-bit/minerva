from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
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
    await create_missing_tables()
    app.state.arq_pool = None
    try:
        app.state.arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    except OSError:
        pass
    except Exception:
        pass
    yield
    pool = getattr(app.state, "arq_pool", None)
    if pool is not None:
        await pool.close()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
register_exception_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api)
