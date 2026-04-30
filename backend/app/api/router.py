"""Aggregates FastAPI routers for health checks, auth, AI, rules, and system modules."""

from fastapi import APIRouter

from app.api.routers import auth, health, probe
from app.s3.api.router import router as s3_files_router
from app.sys.dict.api.router import router as dicts_router
from app.sys.file_storage.api.router import router as file_storages_router
from app.rule.api.router import router as rule_base_router
from app.rule.api.rule_config_prompt_router import router as rule_config_prompt_router
from app.sys.model_provider.api.router import router as model_providers_router
from app.file_ocr.api.router import file_router as ocr_files_router
from app.sys.tool.ocr.api.router import router as ocr_tools_router
from app.ai_api.api.router import router as ai_router

api = APIRouter()
api.include_router(health.router)
api.include_router(probe.router)
api.include_router(auth.router)
api.include_router(ocr_tools_router)
api.include_router(ocr_files_router)
api.include_router(ai_router)
api.include_router(model_providers_router)
api.include_router(file_storages_router)
api.include_router(s3_files_router)
api.include_router(dicts_router)
api.include_router(rule_base_router)
api.include_router(rule_config_prompt_router)
