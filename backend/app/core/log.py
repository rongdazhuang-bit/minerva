"""Log4j-style logger factory and MinervaLogger wrapper."""

from __future__ import annotations

import logging
from typing import Any

from app.core.log_placeholders import format_placeholders

# Stdlib logging kwargs that must not be treated as structured fields.
_RESERVED_KWARGS = frozenset({"exc_info", "stack_info", "stacklevel", "extra"})
# Cached wrappers keyed by logger name.
_LOGGER_CACHE: dict[str, MinervaLogger] = {}


class MinervaLogger:
    """Thin wrapper around stdlib Logger with {} placeholders and kwargs extras."""

    def __init__(self, underlying: logging.Logger) -> None:
        """Bind one stdlib logger instance."""

        self._underlying = underlying

    @property
    def name(self) -> str:
        """Return the wrapped logger name."""

        return self._underlying.name

    def is_enabled_for(self, level: int) -> bool:
        """Return whether the wrapped logger accepts the given level."""

        return self._underlying.isEnabledFor(level)

    def debug(self, msg: str, *args: object, **kwargs: Any) -> None:
        """Log a DEBUG message."""

        self._emit(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args: object, **kwargs: Any) -> None:
        """Log an INFO message."""

        self._emit(logging.INFO, msg, *args, **kwargs)

    def warn(self, msg: str, *args: object, **kwargs: Any) -> None:
        """Log a WARNING message (log4j-style alias)."""

        self._emit(logging.WARNING, msg, *args, **kwargs)

    def warning(self, msg: str, *args: object, **kwargs: Any) -> None:
        """Log a WARNING message."""

        self._emit(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args: object, **kwargs: Any) -> None:
        """Log an ERROR message."""

        self._emit(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args: object, **kwargs: Any) -> None:
        """Log a CRITICAL message."""

        self._emit(logging.CRITICAL, msg, *args, **kwargs)

    def exception(self, msg: str, *args: object, **kwargs: Any) -> None:
        """Log an ERROR message with exception info."""

        if "exc_info" not in kwargs:
            kwargs["exc_info"] = True
        self._emit(logging.ERROR, msg, *args, **kwargs)

    def _emit(self, level: int, msg: str, *args: object, **kwargs: Any) -> None:
        """Format placeholders, merge extras, and delegate to stdlib."""

        reserved = {key: kwargs.pop(key) for key in list(kwargs) if key in _RESERVED_KWARGS}
        result = format_placeholders(msg, *args)
        if not result.matched:
            self._underlying.log(
                logging.WARNING,
                (
                    f"log placeholder mismatch template={msg!r} "
                    f"expected={result.expected} provided={result.provided}"
                ),
                stacklevel=(reserved.get("stacklevel") or 1) + 2,
            )
            message = result.message
        else:
            message = result.message

        merged_extra: dict[str, Any] = dict(reserved.get("extra") or {})
        merged_extra.update(kwargs)

        log_kwargs: dict[str, Any] = {
            "stacklevel": (reserved.get("stacklevel") or 1) + 2,
        }
        if "exc_info" in reserved:
            log_kwargs["exc_info"] = reserved["exc_info"]
        if "stack_info" in reserved:
            log_kwargs["stack_info"] = reserved["stack_info"]
        if merged_extra:
            log_kwargs["extra"] = merged_extra

        self._underlying.log(level, message, **log_kwargs)


def get_logger(name: str) -> MinervaLogger:
    """Return a cached MinervaLogger for the given stdlib logger name."""

    cached = _LOGGER_CACHE.get(name)
    if cached is None:
        cached = MinervaLogger(logging.getLogger(name))
        _LOGGER_CACHE[name] = cached
    return cached
