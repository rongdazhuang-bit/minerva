"""高德 Web 服务 API 客户端（IP 定位、行政区域、天气查询）。"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.core.log import get_logger

log = get_logger(__name__)

_AMAP_BASE_URL = "https://restapi.amap.com/v3"
_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


def _missing_key_response() -> dict[str, Any]:
    """Return a standard error payload when the Amap API key is not configured."""

    return {"ok": False, "error": "AMAP_WEB_SERVICE_KEY 未配置"}


def _configured_key() -> str:
    """Return the trimmed Amap Web Service API key from settings."""

    return (settings.amap_web_service_key or "").strip()


def _parse_amap_response(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize Amap JSON into the skill tool ok/error contract."""

    status = str(data.get("status", ""))
    infocode = str(data.get("infocode", ""))
    if status == "1" and infocode == "10000":
        return {"ok": True, **data}
    info = str(data.get("info", "高德 API 请求失败"))
    return {"ok": False, "error": info, "infocode": infocode, "info": info}


async def _amap_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """Perform one authenticated GET against the Amap Web Service API."""

    key = _configured_key()
    if not key:
        return _missing_key_response()
    query = {"key": key, "output": "JSON", **params}
    url = f"{_AMAP_BASE_URL}/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.get(url, params=query)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        log.warning("amap request timeout path={}", path)
        return {"ok": False, "error": "请求超时"}
    except httpx.HTTPError as exc:
        log.warning("amap http error path={} err={}", path, exc)
        return {"ok": False, "error": "网络请求失败"}
    except ValueError:
        log.warning("amap invalid json path={}", path)
        return {"ok": False, "error": "响应解析失败"}
    if not isinstance(data, dict):
        return {"ok": False, "error": "响应格式无效"}
    return _parse_amap_response(data)


async def lookup_ip(*, ip: str | None = None) -> dict[str, Any]:
    """Locate a domestic IPv4 address via Amap IP geolocation."""

    params: dict[str, Any] = {}
    if ip and ip.strip():
        params["ip"] = ip.strip()
    result = await _amap_get("ip", params)
    if not result.get("ok"):
        return result
    return {
        "ok": True,
        "province": result.get("province", ""),
        "city": result.get("city", ""),
        "adcode": result.get("adcode", ""),
        "rectangle": result.get("rectangle", ""),
    }


async def search_district(*, keywords: str, subdistrict: int = 0) -> dict[str, Any]:
    """Search administrative districts by keyword and return matching nodes."""

    kw = (keywords or "").strip()
    if not kw:
        return {"ok": False, "error": "keywords 不能为空"}
    result = await _amap_get(
        "config/district",
        {
            "keywords": kw,
            "subdistrict": max(0, subdistrict),
            "extensions": "base",
        },
    )
    if not result.get("ok"):
        return result
    districts = result.get("districts")
    if not isinstance(districts, list):
        districts = []
    return {"ok": True, "districts": districts}


async def get_weather(*, city_adcode: str, extensions: str = "all") -> dict[str, Any]:
    """Query live and forecast weather for a city adcode."""

    adcode = (city_adcode or "").strip()
    if not adcode:
        return {"ok": False, "error": "city_adcode 不能为空"}
    ext = (extensions or "all").strip().lower()
    if ext not in {"base", "all"}:
        ext = "all"
    result = await _amap_get(
        "weather/weatherInfo",
        {"city": adcode, "extensions": ext},
    )
    if not result.get("ok"):
        return result
    payload: dict[str, Any] = {"ok": True, "extensions": ext}
    if ext == "base":
        payload["lives"] = result.get("lives", [])
    else:
        payload["lives"] = result.get("lives", [])
        payload["forecasts"] = result.get("forecasts", [])
    return payload
