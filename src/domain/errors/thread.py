"""Thread-related domain errors."""

from src.domain.errors.base import DomainError
from src.domain.errors.codes import ErrorCode


class ThreadNotFoundError(DomainError):
    """Conversation thread not found."""

    status_code = ErrorCode.NOT_FOUND
