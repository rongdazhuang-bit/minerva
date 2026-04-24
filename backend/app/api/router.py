from fastapi import APIRouter

from app.api.routers import auth, health, probe
from app.tool.ocr.api.router import router as ocr_tools_router

api = APIRouter()
api.include_router(health.router)
api.include_router(probe.router)
api.include_router(auth.router)
api.include_router(ocr_tools_router)
