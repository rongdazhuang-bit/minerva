"""Unit tests for shared Celery Redis transport/client options."""

from __future__ import annotations

from app.sys.celery.service import redis_connection as rc


def test_celery_redis_transport_options_include_timeouts() -> None:
    """Broker transport should set connect/socket timeouts and retry_on_timeout."""

    opts = rc.celery_redis_transport_options()
    assert opts["socket_connect_timeout"] >= 5
    assert opts["socket_timeout"] >= 5
    assert opts["retry_on_timeout"] is True
    assert opts["socket_keepalive"] is True
    assert opts["max_connections"] >= 10
    assert "health_check_interval" in opts


def test_verify_celery_broker_unreachable_returns_actionable_message(
    monkeypatch,
) -> None:
    """When PING fails, operators get host/port and broker URL hints."""

    class _Broken:
        def ping(self) -> bool:
            raise ConnectionError("refused")

    monkeypatch.setattr(rc, "create_celery_redis_client", lambda **_: _Broken())
    monkeypatch.setattr(
        rc.settings,
        "celery_broker_url",
        "redis://:secret@127.0.0.1:56379/0",
    )
    ok, message = rc.verify_celery_broker_reachable(attempts=1, delay_seconds=0)
    assert ok is False
    assert "127.0.0.1:56379/0" in message
    assert "CELERY_BROKER_URL=redis://:***@127.0.0.1:56379/0" in message
    assert "queue_declare" in message


def test_celery_redis_client_kwargs_match_transport() -> None:
    """Standalone Redis clients reuse the same timeout settings as Kombu."""

    client_opts = rc.celery_redis_client_kwargs()
    transport_opts = rc.celery_redis_transport_options()
    assert client_opts["socket_connect_timeout"] == transport_opts["socket_connect_timeout"]
    assert client_opts["socket_timeout"] == transport_opts["socket_timeout"]
