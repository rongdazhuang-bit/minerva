"""CORS preflight for private LAN origins in dev-like APP_ENV."""

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_cors_preflight_private_lan_origin() -> None:
    """Dev CORS regex should allow RFC1918 frontend origins (e.g. phone on Wi-Fi)."""
    assert settings.app_env in ("dev", "development", "local", "test")
    client = TestClient(app)
    origin = "http://192.168.1.100:5173"
    res = client.options(
        "/healthz",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == origin
