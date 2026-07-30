"""Outbound port: AgentRunner.

The runner is the LLM/graph boundary. It captures a full conversation turn as
a stream of :class:`~src.domain.entities.trace_event.TraceEvent` records:
HUMAN_MESSAGE first, intermediate events (THINKING/CONTENT/TOOL_CALL/
TOOL_RESULT), then a final AI_MESSAGE.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from src.domain.entities.hitl_decision import HitlDecision
from src.domain.entities.message import Message
from src.domain.entities.trace_event import TraceEvent


class AgentRunner(ABC):
    """Outbound port implemented by the deep-agent infrastructure adapter."""

    @abstractmethod
    async def invoke(self, thread_id: str, message: str, turn_id: str) -> tuple[Message, list[TraceEvent]]:
        """Invoke the agent and return the final Message + the full trace of events.

        Args:
            thread_id: The conversation thread identifier.
            message: The human message text to send to the agent.
            turn_id: Identifier grouping all events of this turn.

        Returns:
            A tuple ``(final_message, trace_events)`` where ``final_message`` is the
            AI :class:`Message` reconstructed from the trailing AI_MESSAGE event,
            and ``trace_events`` is the full ordered list of TraceEvents.
        """
        ...

    @abstractmethod
    def stream(self, thread_id: str, message: str, turn_id: str) -> AsyncIterator[TraceEvent]:
        """Stream all TraceEvents of a turn.

        Emits HUMAN_MESSAGE first, intermediate events (THINKING, CONTENT,
        TOOL_CALL, TOOL_RESULT) as they arrive from the graph, then AI_MESSAGE
        as the trailing event.

        Args:
            thread_id: The conversation thread identifier.
            message: The human message text to send to the agent.
            turn_id: Identifier grouping all events of this turn.

        Yields:
            TraceEvent instances in turn order.
        """
        ...

    @abstractmethod
    async def resume_hitl(
        self, thread_id: str, decisions: list[HitlDecision], turn_id: str
    ) -> tuple[Message, list[TraceEvent]]:
        """Resume a paused HITL turn with the human decisions.

        Args:
            thread_id: The conversation thread identifier.
            decisions: One :class:`HitlDecision` per interrupted tool call, in
                the positional order of the pending action requests.
            turn_id: Identifier grouping all events of this turn.

        Returns:
            A tuple ``(final_message, trace_events)`` where ``final_message``
            is the resulting AI :class:`Message` and ``trace_events`` is the
            full ordered list of TraceEvents (HITL_DECISION events first, then
            intermediate events, then a trailing AI_MESSAGE).

        Raises:
            AgentError: When there is no pending interrupt, when a decision
                references an unknown tool call id, when decisions are missing
                for some interrupted tool calls, or on graph failure.
        """
        ...

    # ------------------------------------------------------------------ #
    # Deprecated single-decision HITL helpers (kept as concrete passthroughs
    # for backward compatibility). New code should call ``resume_hitl`` with
    # a list of :class:`HitlDecision`. These wrappers build a one-element
    # decisions list and delegate to ``resume_hitl``.
    # ------------------------------------------------------------------ #

    async def approve_hitl(self, thread_id: str, tool_call_id: str) -> Message:
        """Deprecated: approve a single interrupted tool call via ``resume_hitl``."""
        message, _ = await self.resume_hitl(
            thread_id, [HitlDecision(tool_call_id=tool_call_id, action="approve")], turn_id=""
        )
        return message

    async def reject_hitl(self, thread_id: str, tool_call_id: str, reason: str | None = None) -> Message:
        """Deprecated: reject a single interrupted tool call via ``resume_hitl``."""
        message, _ = await self.resume_hitl(
            thread_id, [HitlDecision(tool_call_id=tool_call_id, action="reject", reason=reason)], turn_id=""
        )
        return message

    async def edit_hitl(self, thread_id: str, tool_call_id: str, edits: dict) -> Message:
        """Deprecated: edit a single interrupted tool call via ``resume_hitl``."""
        message, _ = await self.resume_hitl(
            thread_id, [HitlDecision(tool_call_id=tool_call_id, action="edit", edits=edits)], turn_id=""
        )
        return message
