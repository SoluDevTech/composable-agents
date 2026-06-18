"""Storage / persistence domain errors."""

from src.domain.errors.base import DomainError
from src.domain.errors.codes import ErrorCode


class StorageError(DomainError):
    """Storage infrastructure error (database, object store)."""

    status_code = ErrorCode.SERVICE_UNAVAILABLE
