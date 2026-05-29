"""Exceptions raised by the MinerU FastAPI HTTP client."""

from __future__ import annotations


class MineruError(Exception):
    """Base class for MinerU client failures."""


class MineruTransportError(MineruError):
    """HTTP failure: non-success status or network error."""

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
        """Serialize with HTTP context for worker ``remark`` / UI."""
        if (
            self.status_code is not None
            and self.url
            and self.body_snippet is not None
        ):
            return (
                f"MinerU response url={self.url} "
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


class MineruParseError(MineruError):
    """Response body is not a parseable ZIP/JSON MinerU result."""

    def __init__(self, message: str, *, raw_body: str | None = None) -> None:
        """Optionally retain a truncated body for debugging."""
        super().__init__(message)
        self.raw_body = raw_body

    def __str__(self) -> str:
        """Append truncated response body when present."""
        if self.raw_body:
            return f"{super().__str__()} body={self.raw_body}"
        return super().__str__()
