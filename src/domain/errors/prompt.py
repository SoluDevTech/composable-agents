"""Prompt management domain errors."""

from src.domain.errors.base import DomainError
from src.domain.errors.codes import ErrorCode


class PromptError(DomainError):
    """Base error for prompt management operations."""

    status_code = ErrorCode.INTERNAL_SERVER_ERROR


class PromptNotFoundError(PromptError):
    """Prompt identifier not found in the prompt manager."""

    status_code = ErrorCode.NOT_FOUND


class PromptAlreadyExistsError(PromptError):
    """A prompt with the given identifier already exists."""

    status_code = ErrorCode.CONFLICT


class PromptManagerUnavailableError(PromptError):
    """The prompt manager backend is unreachable or returned a server error."""

    status_code = ErrorCode.SERVICE_UNAVAILABLE
