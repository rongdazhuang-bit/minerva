"""Internal probes for tests (include_in_schema=False)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.limits import limiter

router = APIRouter(include_in_schema=False)


class ValidationProbeBody(BaseModel):
    name: str


@router.get("/ratelimit-probe")
@limiter.limit("1/second")
async def ratelimit_probe(request: Request) -> dict[str, str]:
    return {"ok": "true"}


@router.post("/validation-probe")
async def validation_probe(body: ValidationProbeBody) -> dict[str, str]:
    return {"name": body.name}
