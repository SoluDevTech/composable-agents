"""Outbound port: AgentRunner.

The runner is the LLM/graph boundary. It captures a full conversation turn as
a stream of :class:`~src.domain.entities.trace_event.TraceEvent` records:
HUMAN_MESSAGE first, intermediate events (THINKING/CONTENT/TOOL_CALL/
TOOL_RESULT), then a final AI_MESSAGE.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

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
    async def approve_hitl(self, thread_id: str, tool_call_id: str) -> Message: ...

    @abstractmethod
    async def reject_hitl(self, thread_id: str, tool_call_id: str, reason: str | None = None) -> Message: ...

    @abstractmethod
    async def edit_hitl(self, thread_id: str, tool_call_id: str, edits: dict) -> Message: ...
