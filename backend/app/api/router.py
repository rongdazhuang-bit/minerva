from fastapi import APIRouter

from app.api.routers import health, probe

api = APIRouter()
api.include_router(health.router)
api.include_router(probe.router)
