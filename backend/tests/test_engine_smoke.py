import uuid

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.domain.execution.engine import run_execution_steps
from app.domain.execution.models import Execution
from app.domain.execution.services import start_execution
from app.infrastructure.db.session import async_session_factory
from app.main import app


def _wid_from_token(token: str) -> uuid.UUID:
    p = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    return uuid.UUID(str(p["wid"]))


@pytest.mark.asyncio
async def test_engine_runs_published_start_to_end() -> None:
    email = f"e{uuid.uuid4().hex}@example.com"
    flow_ok = {
        "schema_version": 1,
        "nodes": [
            {"id": "a", "type": "start", "data": {}},
            {"id": "b", "type": "end", "data": {}},
        ],
        "edges": [{"id": "e1", "source": "a", "target": "b"}],
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        reg = await ac.post(
            "/auth/register",
            json={"email": email, "password": "secret1234"},
        )
        assert reg.status_code == 201, reg.text
        tok = reg.json()["access_token"]
        wid = _wid_from_token(tok)
        h = {"Authorization": f"Bearer {tok}"}
        cr = await ac.post(
            f"/workspaces/{wid}/rules",
            headers=h,
            json={"name": "E1", "type": "document_review", "flow_json": {}},
        )
        assert cr.status_code == 201, cr.text
        rule_id = cr.json()["id"]
        v2 = await ac.post(
            f"/workspaces/{wid}/rules/{rule_id}/versions",
            headers=h,
            json={"flow_json": flow_ok},
        )
        assert v2.status_code == 201, v2.text
        vid = v2.json()["id"]
        pub = await ac.post(
            f"/workspaces/{wid}/rules/{rule_id}/versions/{vid}/publish",
            headers=h,
        )
        assert pub.status_code == 200, pub.text
    eid: uuid.UUID | None = None
    async with async_session_factory() as s:
        ex = await start_execution(
            s,
            workspace_id=wid,
            rule_id=rule_id,
            input_json={},
        )
        eid = ex.id
        await s.commit()
    assert eid is not None
    async with async_session_factory() as s2:
        await run_execution_steps(s2, execution_id=eid)
        await s2.commit()
    async with async_session_factory() as s3:
        ex2 = await s3.get(Execution, eid)
        assert ex2 is not None
        assert ex2.status == "succeeded"
