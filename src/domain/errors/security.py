from src.domain.errors.base import DomainError
from src.domain.errors.codes import ErrorCode

class SecurityError(DomainError):
    """Base error for security concerns."""

    status_code = ErrorCode.INTERNAL_SERVER_ERROR

class InvalidApiKeyError(SecurityError):
    """Error when api key sent by client is not matching"""

    status_code = ErrorCode.UNAUTHORIZED
