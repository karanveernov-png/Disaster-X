"""
Domain exception hierarchy.

Raised by services; caught and mapped to HTTP responses by the
FastAPI exception handlers registered in app/middleware/error_handlers.py.

Never include SQL, stack traces, or credentials in the `message` —
it reaches the API client verbatim.
"""

from __future__ import annotations


class AppError(Exception):
    """Base for all application-level errors."""
    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str = "An unexpected error occurred") -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status_code = 404
    error_code = "not_found"

    def __init__(self, resource: str = "Resource", resource_id: str | None = None) -> None:
        msg = f"{resource} '{resource_id}' not found" if resource_id else f"{resource} not found"
        super().__init__(msg)


class ConflictError(AppError):
    status_code = 409
    error_code = "conflict"


class ValidationError(AppError):
    status_code = 422
    error_code = "validation_error"

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class AuthenticationError(AppError):
    status_code = 401
    error_code = "authentication_required"

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message)


class AuthorizationError(AppError):
    status_code = 403
    error_code = "forbidden"

    def __init__(self, message: str = "You do not have permission to perform this action") -> None:
        super().__init__(message)


class RateLimitError(AppError):
    status_code = 429
    error_code = "rate_limit_exceeded"

    def __init__(self, message: str = "Too many requests. Please try again later.") -> None:
        super().__init__(message)
