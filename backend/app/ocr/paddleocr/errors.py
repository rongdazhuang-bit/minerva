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

    def __str__(self) -> str:
        """Serialize like client INFO logs so worker ``remark`` / UI show full HTTP context."""
        if (
            self.status_code is not None
            and self.url
            and self.body_snippet is not None
        ):
            return (
                f"PaddleOCR-VL response url={self.url} "
                f"http_status={self.status_code} body={self.body_snippet}"
            )
        parts: list[str] = [super().__str__()]
        if self.url:
            parts.append(f"url={self.url}")
        if self.status_code is not None:
            parts.append(f"http_status={self.status_code}")
        if self.body_snippet:
            parts.append(f"body={self.body_snippet}")
        return " ".join(parts) if len(parts) > 1 else parts[0]


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

    def __str__(self) -> str:
        """Include upstream ids and body snippet for persistence (e.g. ``ocr_file.remark``)."""
        parts: list[str] = [super().__str__()]
        if self.log_id is not None:
            parts.append(f"log_id={self.log_id}")
        if self.error_code is not None:
            parts.append(f"error_code={self.error_code}")
        if self.raw_body:
            parts.append(f"body={self.raw_body}")
        return " ".join(parts)


class PaddleOcrVlParseError(PaddleOcrVlError):
    """Response body is not JSON or does not match the expected Pydantic schema."""

    def __init__(self, message: str, *, raw_body: str | None = None) -> None:
        """Optionally retain a truncated body for debugging."""
        super().__init__(message)
        self.raw_body = raw_body

    def __str__(self) -> str:
        """Append truncated response body when present (matches transport-style diagnostics)."""
        if self.raw_body:
            return f"{super().__str__()} body={self.raw_body}"
        return super().__str__()
