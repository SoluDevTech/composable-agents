"""SendMessageUseCase — send a message or HITL decisions to the agent.

The use case depends on TraceEventRepository + the runner API
``invoke(thread_id, message, turn_id) -> (Message, list[TraceEvent])`` and the
unified HITL resume method
``resume_hitl(thread_id, decisions, turn_id) -> (Message, list[TraceEvent])``.
The full trace is persisted in a single batch via ``trace_repo.add_batch`` for
both the human-message and the HITL resume paths.
"""

import logging
import time
import uuid
from typing import Any

from src.domain.entities.hitl_decision import HitlDecision
from src.domain.entities.message import Message
from src.domain.errors.hitl import InvalidHitlActionError
from src.domain.errors.messages import ErrorMessage
from src.domain.logging.messages import LogMessage
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.thread_repository import ThreadRepository
from src.domain.ports.trace_event_repository import TraceEventRepository

logger = logging.getLogger(__name__)


class SendMessageUseCase:
    """Send a human message or HITL decisions to the agent and return the response.

    For a human message: generates a fresh ``turn_id``, invokes the runner,
    persists the full trace in a batch, and returns the final AI Message.

    For HITL decisions (approve/reject/edit, single or multiple): generates a
    fresh ``turn_id``, calls ``runner.resume_hitl`` with the decisions list,
    persists the returned trace in a batch, and returns the final AI Message.
    The legacy single-decision shape (``action`` + ``tool_call_id`` +
    optional ``reason``/``edits``) is converted into a one-element decisions
    list for backward compatibility.
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
        tool_call_id: str | None = None,
        reason: str | None = None,
        edits: dict[str, Any] | None = None,
        decisions: list[HitlDecision] | None = None,
    ) -> Message:
        """Execute the use case.

        Args:
            thread_id: Conversation thread identifier.
            message: Human message text (mutually exclusive with HITL fields).
            action: Legacy single HITL action ("approve", "reject", "edit").
            tool_call_id: Tool call id targeted by a legacy single HITL decision.
            reason: Optional reject reason (legacy single decision).
            edits: Edited args for the "edit" action (legacy single decision).
            decisions: List of HITL decisions (new multi-decision contract).

        Returns:
            The final AI Message.

        Raises:
            InvalidHitlActionError: If ``action`` is not a supported HITL action.
            AgentError: On runner failure.
            ThreadNotFoundError: If the thread does not exist.
        """
        is_hitl = message is None
        if is_hitl and decisions is None and action not in {"approve", "reject", "edit"}:
            raise InvalidHitlActionError(ErrorMessage.INVALID_HITL_ACTION.format(action=action))

        thread = await self._threads.get(thread_id)
        runner = await self._registry.get_runner(thread.agent_name)

        if message is not None:
            logger.info(LogMessage.CHAT_SENDING_HUMAN, thread_id, thread.agent_name)
            turn_id = str(uuid.uuid4())
            start = time.monotonic()
            final_message, trace = await runner.invoke(thread_id, message, turn_id)
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

        if decisions is None:
            decisions = [HitlDecision(tool_call_id=tool_call_id, action=action, reason=reason, edits=edits)]  # type: ignore[arg-type]

        logger.info(LogMessage.CHAT_HITL_RECEIVED, thread_id, thread.agent_name, "decisions", len(decisions))
        turn_id = str(uuid.uuid4())
        start = time.monotonic()
        final_message, trace = await runner.resume_hitl(thread_id, decisions, turn_id)
        await self._trace_repo.add_batch(thread_id, trace)
        elapsed = time.monotonic() - start
        logger.info(LogMessage.CHAT_HITL_COMPLETE, thread_id, thread.agent_name, elapsed, final_message.status)
        return final_message
