"""Aggregates FastAPI routers for health checks, auth, LLM, rules, and system modules."""

from fastapi import APIRouter

from app.core.api.routers import auth
from app.local.api.router import router as local_files_router
from app.s3.api.router import router as s3_files_router
from app.sys.dict.api.router import router as dicts_router
from app.sys.menu.api.router import router as menus_router
from app.sys.role.api.router import platform_router as roles_platform_router
from app.sys.role.api.router import tenant_router as roles_tenant_router
from app.sys.user.api.platform_router import router as users_platform_router
from app.sys.user.api.router import router as users_router
from app.sys.tenant.api.router import router as tenants_router
from app.sys.file_storage.api.router import router as file_storages_router
from app.rule.api.router import router as rule_base_router
from app.rule.api.rule_config_prompt_router import router as rule_config_prompt_router
from app.sys.model_provider.api.router import router as model_providers_router
from app.file_ocr.api.router import file_router as ocr_files_router
from app.mcp.api.router import router as mcp_router
from app.sys.tool.ocr.api.router import router as ocr_tools_router
from app.llm.api.router import router as llm_router
from app.agent.api.v2.router import router as agent_router
from app.translate.api.router import router as translate_router
from app.sys.celery.api.router import router as celery_jobs_router
from app.dataset.api.router import router as datasets_router
from app.sys.permission.api.router import router as permissions_router

api = APIRouter()
api.include_router(auth.router)
api.include_router(ocr_tools_router)
api.include_router(mcp_router)
api.include_router(ocr_files_router)
api.include_router(llm_router)
api.include_router(agent_router)
api.include_router(translate_router)
api.include_router(model_providers_router)
api.include_router(file_storages_router)
api.include_router(s3_files_router)
api.include_router(local_files_router)
api.include_router(dicts_router)
api.include_router(menus_router)
api.include_router(roles_platform_router)
api.include_router(roles_tenant_router)
api.include_router(users_platform_router)
api.include_router(users_router)
api.include_router(tenants_router)
api.include_router(rule_base_router)
api.include_router(rule_config_prompt_router)
api.include_router(celery_jobs_router)
api.include_router(datasets_router)
api.include_router(permissions_router)
