import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_validation_error_uses_envelope():
    """POST body fails Pydantic -> 422 + ErrorBody (Task 4)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post("/validation-probe", json={})
    assert r.status_code == 422
    data = r.json()
    assert data["code"] == "request.validation"
    assert data["type"] == "validation"
    assert "errors" in (data.get("details") or {})


@pytest.mark.asyncio
async def test_ratelimit_probe_second_request_429():
    """SlowAPI: second hit within 1s on same key -> 429."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r1 = await ac.get("/ratelimit-probe")
        r2 = await ac.get("/ratelimit-probe")
    assert r1.status_code == 200
    assert r2.status_code == 429
