"""LLM-related domain errors.

Raised when a user tries to run an agent without configuring an LLM provider.
"""

from src.domain.errors.base import DomainError
from src.domain.errors.codes import ErrorCode


class LlmError(DomainError):
    """Base error for LLM configuration concerns."""

    status_code = ErrorCode.UNPROCESSABLE_ENTITY


class LlmNotConfiguredError(LlmError):
    """Raised when no LLM provider is configured for the authenticated user.

    Mapped to HTTP 422 by the generic domain-error handler. The user must
    configure their provider via ``PUT /api/v1/settings/llm`` before invoking
    any agent.
    """

    status_code = ErrorCode.UNPROCESSABLE_ENTITY
