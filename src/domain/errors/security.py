from src.domain.errors.base import DomainError
from src.domain.errors.codes import ErrorCode


class SecurityError(DomainError):
    """Base error for security concerns."""

    status_code = ErrorCode.INTERNAL_SERVER_ERROR


class InvalidApiKeyError(SecurityError):
    """Error when api key sent by client is not matching"""

    status_code = ErrorCode.UNAUTHORIZED


class AuthenticationError(SecurityError):
    """Raised when no valid credentials (JWT or API key) could be resolved.

    Mapped to HTTP 401 by the generic domain-error handler.
    """

    status_code = ErrorCode.UNAUTHORIZED


class ApiKeyError(SecurityError):
    """Raised for invalid API-key management input (e.g. empty name).

    Mapped to HTTP 422 by the generic domain-error handler.
    """

    status_code = ErrorCode.UNPROCESSABLE_ENTITY


class ApiKeyNotFoundError(SecurityError):
    """Raised when an API key does not exist (or is owned by another user).

    Mapped to HTTP 404 by the generic domain-error handler.
    """

    status_code = ErrorCode.NOT_FOUND
