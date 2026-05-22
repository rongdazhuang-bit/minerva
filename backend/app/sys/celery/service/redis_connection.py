"""Shared Redis client/transport options for Celery broker and auxiliary pub/sub."""

from __future__ import annotations

import re
import sys
import time
from typing import Any
from urllib.parse import urlparse

from app.config import settings


def _broker_redis_endpoint_hint() -> str:
    """Return ``host:port/db`` from ``CELERY_BROKER_URL`` for operator-facing messages."""

    parsed = urlparse(settings.celery_broker_url)
    host = parsed.hostname or "?"
    port = parsed.port or 6379
    db = (parsed.path or "/0").lstrip("/") or "0"
    return f"{host}:{port}/{db}"


def celery_redis_transport_options() -> dict[str, Any]:
    """Build Kombu ``broker_transport_options`` / result backend transport options."""

    opts: dict[str, Any] = {
        "socket_connect_timeout": int(settings.celery_redis_socket_connect_timeout),
        "socket_timeout": int(settings.celery_redis_socket_timeout),
        "retry_on_timeout": True,
        "health_check_interval": int(settings.celery_redis_health_check_interval),
        "max_connections": 20,
        # Reduce idle disconnects on Windows / NAT (WinError 10053) during long-lived workers.
        "socket_keepalive": True,
    }
    return opts


def celery_redis_client_kwargs(*, decode_responses: bool = True) -> dict[str, Any]:
    """Keyword arguments for ``redis.Redis.from_url`` used outside Kombu."""

    return {
        "decode_responses": decode_responses,
        "socket_connect_timeout": int(settings.celery_redis_socket_connect_timeout),
        "socket_timeout": int(settings.celery_redis_socket_timeout),
        "retry_on_timeout": True,
        "health_check_interval": int(settings.celery_redis_health_check_interval),
    }


def create_celery_redis_client(*, decode_responses: bool = True) -> Any:
    """Return one Redis client configured like the Celery broker connection."""

    import redis

    return redis.Redis.from_url(
        settings.celery_broker_url,
        **celery_redis_client_kwargs(decode_responses=decode_responses),
    )


def verify_celery_broker_reachable(
    *,
    attempts: int = 3,
    delay_seconds: float = 2.0,
) -> tuple[bool, str]:
    """Ping broker Redis; return ``(ok, message)`` for scripts and startup diagnostics.

    Kombu ``queue_declare`` / ``pipe.execute()`` failures during Worker pidbox setup
    usually mean the broker is down, auth failed, or the TCP session was reset (e.g.
    WinError 10053 on Windows). This helper surfaces a concise cause before Celery logs
    a long Kombu stack trace.
    """

    endpoint = _broker_redis_endpoint_hint()
    last_exc: Exception | None = None
    tries = max(1, int(attempts))
    for attempt in range(1, tries + 1):
        try:
            client = create_celery_redis_client()
            client.ping()
            return True, f"Celery broker Redis 可达 ({endpoint})"
        except Exception as exc:
            last_exc = exc
            if attempt < tries:
                time.sleep(max(0.0, float(delay_seconds)))
    detail = str(last_exc).strip() if last_exc else "unknown error"
    safe_url = re.sub(r":([^@/]+)@", ":***@", settings.celery_broker_url)
    return (
        False,
        "Celery broker Redis 不可用，Worker/Beat 无法完成队列声明 "
        f"(kombu queue_declare / pipe.execute)。\n"
        f"  目标: {endpoint}\n"
        f"  配置: CELERY_BROKER_URL={safe_url}\n"
        f"  错误: {detail}\n"
        "  请确认 Redis 已启动、端口转发/防火墙允许连接、密码正确；"
        "本地开发若使用 127.0.0.1:56379，需先建立到远程 Redis 的隧道。"
        "仍失败时可设置 CELERY_SKIP_BROKER_PREFLIGHT=1 跳过本检查，"
        "由 Celery 自行重试连接。",
    )
