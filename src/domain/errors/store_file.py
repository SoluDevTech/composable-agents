"""Store file domain errors."""

from src.domain.errors.base import DomainError
from src.domain.errors.codes import ErrorCode


class StoreFileNotFoundError(DomainError):
    """File not found in the store."""

    status_code = ErrorCode.NOT_FOUND
