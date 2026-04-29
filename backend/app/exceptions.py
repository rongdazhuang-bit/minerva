"""Small domain-level exception type used across routers and services."""

class AppError(Exception):
    """Domain / API error with stable client-facing code."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        """Attach stable ``code``, human ``message``, and HTTP ``status_code`` for handlers."""

        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)
