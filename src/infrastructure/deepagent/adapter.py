import json
import logging
import re
import time
from collections.abc import AsyncIterator

from langgraph.types import Command

from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.exceptions import AgentError
from src.domain.ports.agent_runner import AgentRunner
from src.domain.ports.tracing_provider import TracingProvider

logger = logging.getLogger("composable-agents")


class DeepAgentRunner(AgentRunner):
    """Adapter qui execute un Deep Agent LangGraph."""

    def __init__(self, graph, tracing_provider: TracingProvider | None = None):
        self._graph = graph
        self._tracing_provider = tracing_provider

    @staticmethod
    def _try_parse_json(content: str) -> dict | None:
        """Try to extract a JSON object from content that may contain markdown."""
        if not content:
            return None
        # Try direct parse first
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        # Try extracting from ```json ... ``` blocks
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
        return None

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
        messages = result.get("messages", [])
        if not messages:
            raise AgentError("Graph completed but no messages were found in the final state.")
        last_message = messages[-1]

        all_tool_calls = getattr(last_message, "tool_calls", None) or []

        state = self._graph.get_state(config)
        status = MessageStatus.AWAITING_HITL if state.interrupts else MessageStatus.COMPLETED

        structured_response = None
        raw_structured = result.get("structured_response")
        if raw_structured is not None:
            if hasattr(raw_structured, "model_dump"):
                structured_response = raw_structured.model_dump()
            elif isinstance(raw_structured, dict):
                structured_response = raw_structured

        if structured_response is None:
            structured_response = self._try_parse_json(last_message.content)

        return Message(
            role=MessageRole.AI,
            content=last_message.content,
            tool_calls=all_tool_calls or None,
            status=status,
            structured_response=structured_response,
        )

    async def invoke(self, thread_id: str, message: str) -> Message:
        config = self._build_config(thread_id)
        logger.info("[thread=%s] Invoking agent", thread_id)
        logger.debug("[thread=%s] Message: %s", thread_id, message[:200])
        try:
            start = time.monotonic()
            result = await self._graph.ainvoke(
                {"messages": [{"role": "human", "content": message}]},
                config=config,
            )
            elapsed = time.monotonic() - start
            response = self._build_response(result, config)
            logger.info("[thread=%s] Invoke complete, status=%s, elapsed=%.2fs", thread_id, response.status, elapsed)
            return response
        except Exception as e:
            logger.exception("[thread=%s] Agent execution error", thread_id)
            raise AgentError(f"Agent execution error: {e}") from e

    async def _yield_chunks(
        self,
        thread_id: str,
        message: str,
        config: dict,
        stats: dict,
    ) -> AsyncIterator[str]:
        """Stream graph chunks and populate *stats* with timing."""
        start = time.monotonic()
        first_chunk = True
        chunk_count = 0
        async for chunk, _metadata in self._graph.astream(
            {"messages": [{"role": "human", "content": message}]},
            config=config,
            stream_mode="messages",
        ):
            if hasattr(chunk, "content") and chunk.content and chunk.type == "AIMessageChunk":
                if first_chunk:
                    logger.info(
                        "[thread=%s] First chunk received, elapsed=%.2fs",
                        thread_id,
                        time.monotonic() - start,
                    )
                    first_chunk = False
                chunk_count += 1
                yield chunk.content
        stats["chunk_count"] = chunk_count
        stats["elapsed"] = time.monotonic() - start

    async def stream(self, thread_id: str, message: str) -> AsyncIterator[str]:
        config = self._build_config(thread_id)
        logger.info("[thread=%s] Streaming agent response", thread_id)
        try:
            stats: dict = {}
            async for chunk in self._yield_chunks(thread_id, message, config, stats):
                yield chunk
            logger.info(
                "[thread=%s] Stream complete, %d chunks, elapsed=%.2fs",
                thread_id,
                stats["chunk_count"],
                stats["elapsed"],
            )
        except Exception as e:
            logger.exception("[thread=%s] Streaming error", thread_id)
            raise AgentError(f"Streaming error: {e}") from e

    async def stream_with_message(self, thread_id: str, message: str) -> AsyncIterator[str | Message]:
        config = self._build_config(thread_id)
        logger.info("[thread=%s] Streaming agent response with final message", thread_id)
        try:
            stats: dict = {}
            async for chunk in self._yield_chunks(thread_id, message, config, stats):
                yield chunk
            state = self._graph.get_state(config)
            values = state.values if state and hasattr(state, "values") else {}
            result = {
                "messages": values.get("messages", []),
                "structured_response": values.get("structured_response"),
            }
            response = self._build_response(result, config)
            logger.info(
                "[thread=%s] Stream with message complete, %d chunks, elapsed=%.2fs, status=%s",
                thread_id,
                stats["chunk_count"],
                stats["elapsed"],
                response.status,
            )
            yield response
        except Exception as e:
            logger.exception("[thread=%s] Streaming error", thread_id)
            raise AgentError(f"Streaming error: {e}") from e

    async def approve_hitl(self, thread_id: str, tool_call_id: str) -> Message:  # noqa: ARG002
        config = self._build_config(thread_id)
        logger.info("[thread=%s] HITL approve", thread_id)
        try:
            start = time.monotonic()
            result = await self._graph.ainvoke(
                Command(resume={"decisions": [{"type": "approve"}]}),
                config=config,
            )
            elapsed = time.monotonic() - start
            response = self._build_response(result, config)
            logger.info("[thread=%s] HITL approve complete, elapsed=%.2fs", thread_id, elapsed)
            return response
        except Exception as e:
            logger.exception("HITL approve error")
            raise AgentError(f"HITL approve error: {e}") from e

    async def reject_hitl(self, thread_id: str, tool_call_id: str, reason: str | None = None) -> Message:  # noqa: ARG002
        config = self._build_config(thread_id)
        logger.info("[thread=%s] HITL reject, reason=%s", thread_id, reason)
        try:
            start = time.monotonic()
            result = await self._graph.ainvoke(
                Command(resume={"decisions": [{"type": "reject", "message": reason or ""}]}),
                config=config,
            )
            elapsed = time.monotonic() - start
            response = self._build_response(result, config)
            logger.info("[thread=%s] HITL reject complete, elapsed=%.2fs", thread_id, elapsed)
            return response
        except Exception as e:
            logger.exception("HITL reject error")
            raise AgentError(f"HITL reject error: {e}") from e

    async def edit_hitl(self, thread_id: str, tool_call_id: str, edits: dict) -> Message:
        config = self._build_config(thread_id)
        logger.info("[thread=%s] HITL edit, tool_call_id=%s", thread_id, tool_call_id)
        try:
            start = time.monotonic()
            state = self._graph.get_state(config)
            tool_name = tool_call_id
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
            elapsed = time.monotonic() - start
            response = self._build_response(result, config)
            logger.info("[thread=%s] HITL edit complete, elapsed=%.2fs", thread_id, elapsed)
            return response
        except Exception as e:
            logger.exception("HITL edit error")
            raise AgentError(f"HITL edit error: {e}") from e
