"""启动时按模型元数据创建尚未存在的表（不替代 Alembic 的结构性迁移）。"""

from __future__ import annotations

from socket import gaierror

from sqlalchemy.exc import OperationalError

from app.config import settings
from app.core.infrastructure.db.base import Base
from app.core.log import get_logger

log = get_logger(__name__)

# Windows 10061 / 常见 *nix ECONNREFUSED(111) 等：服务未监听
_DB_UNREACH_ERRNOS: frozenset[int] = frozenset(
    {
        10061,  # Windows: connection refused
        10060,  # Windows: timed out
        111,  # Linux/macOS: ECONNREFUSED
    }
)


def _is_db_unavailable(exc: BaseException) -> bool:
    """可判定为「库没起来 / 未监听」的异常；认证失败等不视为可静默跳过。"""

    if isinstance(exc, (ConnectionError, gaierror, TimeoutError)):
        return True
    if isinstance(exc, ConnectionRefusedError):
        return True
    if isinstance(exc, OSError) and exc.errno in _DB_UNREACH_ERRNOS:
        return True
    if isinstance(exc, OperationalError):
        low = str(exc).lower()
        if any(
            k in low
            for k in (
                "password",
                "authentication",
                "denied",
                "invalid",
                "role",
            )
        ):
            return False
        if any(
            k in low
            for k in (
                "refused",
                "connection refused",
                "could not connect",
                "connect call failed",
            )
        ):
            return True
    c = exc.__cause__ or exc.__context__
    if c is not None and c is not exc:
        return _is_db_unavailable(c)
    return False


def _dev_like_env() -> bool:
    return (settings.app_env or "dev").lower() in (
        "dev",
        "development",
        "local",
        "test",
    )


def _import_models() -> None:
    import app.core.domain.authorization.models  # noqa: F401
    import app.core.domain.identity.models  # noqa: F401
    import app.sys.dict.domain.db.models  # noqa: F401
    import app.sys.menu.domain.db.models  # noqa: F401
    import app.sys.role.domain.db.models  # noqa: F401
    import app.sys.user.domain.db.models  # noqa: F401
    import app.sys.file_storage.domain.db.models  # noqa: F401
    import app.sys.model_provider.domain.db.models  # noqa: F401
    import app.rule.domain.db.models  # noqa: F401
    import app.file_ocr.domain.db.models  # noqa: F401
    import app.file_ocr.domain.db.models_log  # noqa: F401
    import app.file_ocr.domain.db.models_result  # noqa: F401
    import app.sys.tool.ocr.domain.db.models  # noqa: F401
    import app.mcp.domain.db.models  # noqa: F401
    import app.agent.domain.db.models  # noqa: F401
    import app.translate.domain.db.models  # noqa: F401
    import app.dataset.domain.db.models  # noqa: F401


async def create_missing_tables() -> None:
    """Create missing ORM tables when enabled by settings."""

    if not settings.auto_create_tables:
        log.info("database bootstrap skipped", event="db.bootstrap.skipped")
        return
    _import_models()
    from app.core.infrastructure.db.session import engine

    log.info("database bootstrap started", event="db.bootstrap.started")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.create_all,
                checkfirst=True,
            )
    except Exception as e:
        if not (_dev_like_env() and _is_db_unavailable(e)):
            log.exception("database bootstrap failed", event="db.bootstrap.failed")
            raise
        log.warn(
            "无法连接 PostgreSQL，开发环境已跳过启动建表（AUTO_CREATE_TABLES 仍为真）。"
            "请启动数据库后重启，或先设置 AUTO_CREATE_TABLES=false；业务接口仍需要可用的数据库。",
            event="db.bootstrap.skipped_unavailable",
        )
        log.debug("跳过建表原因", exc_info=e)
        return
    log.info("database bootstrap finished", event="db.bootstrap.finished")
