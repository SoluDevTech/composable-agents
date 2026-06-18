"""Agent-related domain errors."""

from src.domain.errors.base import DomainError
from src.domain.errors.codes import ErrorCode


class AgentError(DomainError):
    """Agent execution error (LLM failure, graph error)."""

    status_code = ErrorCode.BAD_GATEWAY


class AgentNotFoundError(AgentError):
    """Agent not found."""

    status_code = ErrorCode.NOT_FOUND


class AgentConfigAlreadyExistsError(DomainError):
    """Agent configuration already exists."""

    status_code = ErrorCode.CONFLICT
