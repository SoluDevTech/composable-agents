"""SendMessageUseCase — send a message or an HITL decision to the agent.

Ticket 3 rewrite: the use case now depends on TraceEventRepository + the new
runner API ``invoke(thread_id, message, turn_id) -> (Message, list[TraceEvent])``.
The full trace is persisted in a single batch via ``trace_repo.add_batch``.
The HITL path (approve/reject/edit) returns the runner Message directly
without persisting trace events.
"""

import logging
import time
import uuid
from typing import Any

from src.domain.entities.message import Message
from src.domain.errors.hitl import InvalidHitlActionError
from src.domain.errors.messages import ErrorMessage
from src.domain.logging.messages import LogMessage
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.thread_repository import ThreadRepository
from src.domain.ports.trace_event_repository import TraceEventRepository

logger = logging.getLogger(__name__)


class SendMessageUseCase:
    """Send a human message or an HITL decision to the agent and return the response.

    For a human message: generates a fresh ``turn_id``, invokes the runner,
    persists the full trace in a batch, and returns the final AI Message.

    For HITL decisions (approve/reject/edit): calls the corresponding runner
    method and returns the Message directly (no trace persistence — HITL does
    not currently emit trace events).
    """

    def __init__(self, registry: AgentRegistry, threads: ThreadRepository, trace_repo: TraceEventRepository) -> None:
        self._registry = registry
        self._threads = threads
        self._trace_repo = trace_repo

    async def execute(
        self,
        thread_id: str,
        *,
        message: str | None = None,
        action: str | None = None,
        tool_call_id: str | None = None,  # noqa: ARG002
        reason: str | None = None,  # noqa: ARG002
        edits: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> Message:
        """Execute the use case.

        Args:
            thread_id: Conversation thread identifier.
            message: Human message text (mutually exclusive with HITL fields).
            action: HITL action ("approve", "reject", "edit").
            tool_call_id: Tool call id targeted by the HITL decision.
            reason: Optional reject reason.
            edits: Edited args for the "edit" action.

        Returns:
            The final AI Message.

        Raises:
            InvalidHitlActionError: If ``action`` is not a supported HITL action.
            AgentError: On runner failure.
            ThreadNotFoundError: If the thread does not exist.
        """
        # Validate HITL action name up-front to keep the 422 contract intact.
        if message is None:
            match action:
                case "approve" | "reject" | "edit":
                    pass
                case _:
                    raise InvalidHitlActionError(ErrorMessage.INVALID_HITL_ACTION.format(action=action))

        thread = await self._threads.get(thread_id)
        runner = await self._registry.get_runner(thread.agent_name)

        if message is not None:
            logger.info(LogMessage.CHAT_SENDING_HUMAN, thread_id, thread.agent_name)
            turn_id = str(uuid.uuid4())
            start = time.monotonic()
            final_message, trace = await runner.invoke(thread_id, message, turn_id)
            # Persist all trace events of the turn in a single batch.
            await self._trace_repo.add_batch(thread_id, trace)
            elapsed = time.monotonic() - start
            logger.info(
                LogMessage.CHAT_INVOKE_COMPLETE,
                thread_id,
                thread.agent_name,
                elapsed,
                final_message.status,
                len(final_message.content or ""),
            )
            return final_message

        # HITL path — returns the runner Message directly, no trace persistence.
        logger.info(LogMessage.CHAT_HITL_RECEIVED, thread_id, thread.agent_name, action, tool_call_id)
        start = time.monotonic()
        match action:
            case "approve":
                response = await runner.approve_hitl(thread_id, tool_call_id)  # type: ignore[arg-type]
            case "reject":
                response = await runner.reject_hitl(thread_id, tool_call_id, reason)  # type: ignore[arg-type]
            case "edit":
                response = await runner.edit_hitl(thread_id, tool_call_id, edits)  # type: ignore[arg-type]
            case _:
                # Defensive — already validated above, but keeps mypy happy.
                raise InvalidHitlActionError(ErrorMessage.INVALID_HITL_ACTION.format(action=action))
        elapsed = time.monotonic() - start
        logger.info(LogMessage.CHAT_HITL_COMPLETE, thread_id, thread.agent_name, elapsed, response.status)
        return response
