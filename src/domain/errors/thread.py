"""Thread-related domain errors."""

from src.domain.errors.base import DomainError
from src.domain.errors.codes import ErrorCode


class ThreadNotFoundError(DomainError):
    """Conversation thread not found."""

    status_code = ErrorCode.NOT_FOUND


class MessageBuildError(DomainError):
    """Cannot build a Message from an incompatible trace event."""

    status_code = ErrorCode.INTERNAL_SERVER_ERROR
