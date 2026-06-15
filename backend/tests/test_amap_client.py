"""Tests for Amap Web Service client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.infrastructure import amap_client


@pytest.fixture
def amap_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure a test Amap API key."""

    monkeypatch.setattr(
        "app.agent.infrastructure.amap_client.settings.amap_web_service_key",
        "test-amap-key",
    )


def _mock_http_json(monkeypatch: pytest.MonkeyPatch, payload: dict) -> AsyncMock:
    """Patch httpx.AsyncClient to return one JSON payload."""

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = payload
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "app.agent.infrastructure.amap_client.httpx.AsyncClient",
        lambda **_kwargs: mock_client,
    )
    return mock_client


@pytest.mark.asyncio
async def test_lookup_ip_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing API key returns a structured error without HTTP."""

    monkeypatch.setattr(
        "app.agent.infrastructure.amap_client.settings.amap_web_service_key",
        "",
    )
    result = await amap_client.lookup_ip()
    assert result == {"ok": False, "error": "AMAP_WEB_SERVICE_KEY 未配置"}


@pytest.mark.asyncio
async def test_lookup_ip_success(amap_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful IP lookup returns province, city, and adcode."""

    _mock_http_json(
        monkeypatch,
        {
            "status": "1",
            "infocode": "10000",
            "province": "山东省",
            "city": "济南市",
            "adcode": "370100",
            "rectangle": "116.0,36.0;117.0,37.0",
        },
    )
    result = await amap_client.lookup_ip(ip="114.247.50.2")
    assert result["ok"] is True
    assert result["city"] == "济南市"
    assert result["adcode"] == "370100"


@pytest.mark.asyncio
async def test_search_district_requires_keywords(amap_key: None) -> None:
    """Empty keywords are rejected before HTTP."""

    result = await amap_client.search_district(keywords="  ")
    assert result == {"ok": False, "error": "keywords 不能为空"}


@pytest.mark.asyncio
async def test_search_district_success(amap_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """District search returns normalized districts list."""

    _mock_http_json(
        monkeypatch,
        {
            "status": "1",
            "infocode": "10000",
            "districts": [{"name": "北京市", "adcode": "110000", "level": "province"}],
        },
    )
    result = await amap_client.search_district(keywords="北京")
    assert result["ok"] is True
    assert result["districts"][0]["adcode"] == "110000"


@pytest.mark.asyncio
async def test_get_weather_success(amap_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Weather query defaults to extensions=all and returns lives and forecasts."""

    _mock_http_json(
        monkeypatch,
        {
            "status": "1",
            "infocode": "10000",
            "lives": [{"city": "北京市", "weather": "晴", "temperature": "25"}],
            "forecasts": [{"city": "北京市", "casts": [{"date": "2026-06-15"}]}],
        },
    )
    result = await amap_client.get_weather(city_adcode="110000")
    assert result["ok"] is True
    assert result["extensions"] == "all"
    assert result["lives"][0]["weather"] == "晴"
    assert result["forecasts"][0]["casts"][0]["date"] == "2026-06-15"


@pytest.mark.asyncio
async def test_amap_api_business_failure(amap_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-success Amap status maps to ok=false."""

    _mock_http_json(
        monkeypatch,
        {"status": "0", "infocode": "10003", "info": "INVALID_USER_KEY"},
    )
    result = await amap_client.lookup_ip()
    assert result["ok"] is False
    assert result["error"] == "INVALID_USER_KEY"
    assert result["infocode"] == "10003"
