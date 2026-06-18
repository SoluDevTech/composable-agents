"""Configuration-related domain errors."""

from src.domain.errors.base import DomainError
from src.domain.errors.codes import ErrorCode


class ConfigError(DomainError):
    """Configuration error (invalid input, malformed file, bad request body)."""

    status_code = ErrorCode.BAD_REQUEST


class ConfigNotFoundError(ConfigError):
    """Configuration file or resource not found."""

    status_code = ErrorCode.NOT_FOUND


class ConfigValidationError(ConfigError):
    """Schema validation error carrying structured error details."""

    status_code = ErrorCode.UNPROCESSABLE_ENTITY

    def __init__(self, errors: list[dict]) -> None:
        self.errors = errors
        messages = [f"  - {e.get('loc', '?')}: {e.get('msg', '?')}" for e in errors]
        super().__init__("Validation errors:\n" + "\n".join(messages))
