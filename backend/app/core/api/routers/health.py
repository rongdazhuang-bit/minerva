"""Public health endpoint for load balancers and uptime checks."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz():
    """Return static OK payload."""

    return {"status": "ok"}
