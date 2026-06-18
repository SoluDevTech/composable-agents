"""Human-in-the-loop domain errors."""

from src.domain.errors.base import DomainError
from src.domain.errors.codes import ErrorCode


class InvalidHitlActionError(DomainError):
    """Invalid HITL action submitted for an interrupted tool call."""

    status_code = ErrorCode.BAD_REQUEST
