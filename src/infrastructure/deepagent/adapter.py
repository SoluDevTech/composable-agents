from typing import AsyncIterator

from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.exceptions import AgentError
from src.domain.ports.agent_runner import AgentRunner
from src.domain.ports.tracing_provider import TracingProvider


class DeepAgentRunner(AgentRunner):
    """Adapter qui execute un Deep Agent LangGraph."""

    def __init__(self, graph, tracing_provider: TracingProvider | None = None):
        self._graph = graph
        self._tracing_provider = tracing_provider

    def _build_config(self, thread_id: str) -> dict:
        """Build the LangGraph config with optional tracing callbacks.

        Args:
            thread_id: The conversation thread identifier.

        Returns:
            Config dict with thread_id and optional callbacks.
        """
        config: dict = {"configurable": {"thread_id": thread_id}}
        if self._tracing_provider:
            callbacks = self._tracing_provider.get_callbacks()
            if callbacks:
                config["callbacks"] = callbacks
        return config

    def _build_response(self, result: dict, config: dict) -> Message:
        """Build a Message from graph result, detecting interrupts and collecting tool_calls."""
        messages = result["messages"]
        last_message = messages[-1]

        all_tool_calls = getattr(last_message, "tool_calls", None) or []

        state = self._graph.get_state(config)
        status = (
            MessageStatus.AWAITING_HITL
            if state.interrupts
            else MessageStatus.COMPLETED
        )
        return Message(
            role=MessageRole.AI,
            content=last_message.content,
            tool_calls=all_tool_calls or None,
            status=status,
        )

    async def invoke(self, thread_id: str, message: str) -> Message:
        """Envoie un message et retourne la reponse complete."""
        config = self._build_config(thread_id)
        try:
            result = await self._graph.ainvoke(
                {"messages": [{"role": "human", "content": message}]},
                config=config,
            )
            return self._build_response(result, config)
        except Exception as e:
            raise AgentError(f"Erreur d'execution de l'agent: {e}") from e

    async def stream(self, thread_id: str, message: str) -> AsyncIterator[str]:
        """Envoie un message et streame la reponse par chunks."""
        config = self._build_config(thread_id)
        try:
            async for event in self._graph.astream(
                {"messages": [{"role": "human", "content": message}]},
                config=config,
                stream_mode="messages-tuple",
            ):
                msg_type, msg = event
                if msg_type == "ai" and hasattr(msg, "content") and msg.content:
                    yield msg.content
        except Exception as e:
            raise AgentError(f"Erreur de streaming: {e}") from e

    async def approve_hitl(self, thread_id: str, tool_call_id: str) -> Message:
        config = self._build_config(thread_id)
        try:
            from langgraph.types import Command
            result = await self._graph.ainvoke(
                Command(resume={"decisions": [{"type": "approve"}]}),
                config=config,
            )
            return self._build_response(result, config)
        except Exception as e:
            raise AgentError(f"Erreur HITL approve: {e}") from e

    async def reject_hitl(self, thread_id: str, tool_call_id: str, reason: str | None = None) -> Message:
        config = self._build_config(thread_id)
        try:
            from langgraph.types import Command
            result = await self._graph.ainvoke(
                Command(resume={"decisions": [{"type": "reject", "message": reason or ""}]}),
                config=config,
            )
            return self._build_response(result, config)
        except Exception as e:
            raise AgentError(f"Erreur HITL reject: {e}") from e

    async def edit_hitl(self, thread_id: str, tool_call_id: str, edits: dict) -> Message:
        config = self._build_config(thread_id)
        try:
            from langgraph.types import Command
            # Resolve tool name from graph state
            state = self._graph.get_state(config)
            tool_name = tool_call_id  # fallback
            for msg in state.values.get("messages", []):
                if hasattr(msg, "tool_calls"):
                    for tc in msg.tool_calls:
                        if tc.get("id") == tool_call_id:
                            tool_name = tc["name"]
                            break
            result = await self._graph.ainvoke(
                Command(resume={"decisions": [{"type": "edit", "edited_action": {"name": tool_name, "args": edits}}]}),
                config=config,
            )
            return self._build_response(result, config)
        except Exception as e:
            raise AgentError(f"Erreur HITL edit: {e}") from e
