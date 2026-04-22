from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.router import api
from app.config import settings
from app.errors import register_exception_handlers
from app.limits import limiter

app = FastAPI(title=settings.app_name)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
register_exception_handlers(app)
app.include_router(api)
