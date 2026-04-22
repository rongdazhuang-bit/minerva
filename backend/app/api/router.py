from fastapi import APIRouter

from app.api.routers import auth, health, probe, rules

api = APIRouter()
api.include_router(health.router)
api.include_router(probe.router)
api.include_router(auth.router)
api.include_router(rules.router)
