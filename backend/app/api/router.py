from fastapi import APIRouter

from app.api.routers import health

api = APIRouter()
api.include_router(health.router)
