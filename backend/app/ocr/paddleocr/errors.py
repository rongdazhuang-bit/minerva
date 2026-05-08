"""Exceptions raised by the PaddleOCR-VL HTTP client (transport, API, and parse errors)."""

from __future__ import annotations


class PaddleOcrVlError(Exception):
    """Base class for PaddleOCR-VL client failures."""


class PaddleOcrVlTransportError(PaddleOcrVlError):
    """HTTP failure: non-success status or network error before a parsed envelope."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        url: str | None = None,
        body_snippet: str | None = None,
    ) -> None:
        """Attach optional HTTP context for callers and logs."""
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.body_snippet = body_snippet


class PaddleOcrVlApiError(PaddleOcrVlError):
    """HTTP 200 (or success path) with ``errorCode != 0`` in the Paddle serving envelope."""

    def __init__(
        self,
        message: str,
        *,
        log_id: str | None = None,
        error_code: int | None = None,
        error_msg: str | None = None,
        raw_body: str | None = None,
    ) -> None:
        """Keep ``logId`` and upstream codes for correlating with Paddle logs."""
        super().__init__(message)
        self.log_id = log_id
        self.error_code = error_code
        self.error_msg = error_msg
        self.raw_body = raw_body


class PaddleOcrVlParseError(PaddleOcrVlError):
    """Response body is not JSON or does not match the expected Pydantic schema."""

    def __init__(self, message: str, *, raw_body: str | None = None) -> None:
        """Optionally retain a truncated body for debugging."""
        super().__init__(message)
        self.raw_body = raw_body
