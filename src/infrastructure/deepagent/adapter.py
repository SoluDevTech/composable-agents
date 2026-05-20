import json
import logging
import re
import time
from collections.abc import AsyncIterator

from langgraph.types import Command
from pydantic import BaseModel

from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.entities.stream_event import StreamEvent, StreamEventType
from src.domain.exceptions import AgentError
from src.domain.ports.agent_runner import AgentRunner
from src.domain.ports.tracing_provider import TracingProvider

logger = logging.getLogger(__name__)


class DeepAgentRunner(AgentRunner):
    def __init__(self, graph, tracing_provider: TracingProvider | None = None, response_format_model: type[BaseModel] | None = None):
        self._graph = graph
        self._tracing_provider = tracing_provider
        self._response_format_model = response_format_model

    @staticmethod
    def _try_parse_json(content: str) -> dict | None:
        if not content:
            return None
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    def _validate_structured_response(self, data: dict) -> dict:
        """Validate structured_response against the response_format model.

        Strips any extra fields not defined in the schema and logs warnings.
        """
        try:
            validated = self._response_format_model.model_validate(data)
            cleaned = validated.model_dump()
            self._log_extra_fields(data, cleaned)
            return cleaned
        except Exception:
            logger.warning("Failed to validate structured_response against schema, returning raw data")
            return data

    @staticmethod
    def _log_extra_fields(original: dict, cleaned: dict) -> None:
        """Log any top-level or nested fields that were stripped."""
        for key in original:
            if key not in cleaned:
                logger.warning("Stripped extra field from structured_response: '%s'", key)
            elif isinstance(original[key], dict) and isinstance(cleaned[key], dict):
                for sub_key in original[key]:
                    if sub_key not in cleaned[key]:
                        logger.warning("Stripped extra nested field: '%s.%s'", key, sub_key)

    @staticmethod
    def _is_nonblank_str(val: object) -> bool:
        return isinstance(val, str) and val.strip() != ""

    @staticmethod
    def _classify_chunk(chunk) -> tuple[StreamEventType, str] | None:
        if chunk.type != "AIMessageChunk":
            return None
        additional = getattr(chunk, "additional_kwargs", {})
        reasoning = additional.get("reasoning_content")
        if DeepAgentRunner._is_nonblank_str(reasoning):
            return (StreamEventType.THINKING, reasoning)
        if additional.get("type") == "thinking" and DeepAgentRunner._is_nonblank_str(chunk.content):
            return (StreamEventType.THINKING, chunk.content)
        if DeepAgentRunner._is_nonblank_str(chunk.content):
            return (StreamEventType.CONTENT, chunk.content)
        return None

    def _build_config(self, thread_id: str) -> dict:
        config: dict = {"configurable": {"thread_id": thread_id}}
        if self._tracing_provider:
            callbacks = self._tracing_provider.get_callbacks()
            if callbacks:
                config["callbacks"] = callbacks
        return config

    def _extract_structured_response(self, messages: list) -> dict | None:
        """Extract structured_response from tool_calls in messages."""
        if not messages:
            return None
        # Walk messages in reverse to find the most recent structured_response tool call
        for msg in reversed(messages):
            tool_calls = getattr(msg, "tool_calls", None) or []
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if tc.get("name") == "structured_response":
                        args = tc.get("args")
                        if args:
                            if isinstance(args, dict):
                                return args
                            if isinstance(args, str):
                                try:
                                    parsed = json.loads(args)
                                    if isinstance(parsed, dict):
                                        return parsed
                                except (json.JSONDecodeError, TypeError):
                                    pass
        return None

    def _build_response(self, result: dict, config: dict, thinking: str | None) -> Message:
        messages = result.get("messages", [])
        if not messages:
            raise AgentError("Graph completed but no messages were found in the final state.")
        last_message = messages[-1]
        all_tool_calls = getattr(last_message, "tool_calls", None) or []
        state = self._graph.get_state(config)
        status = MessageStatus.AWAITING_HITL if state.interrupts else MessageStatus.COMPLETED

        # 1. Try extracting structured_response from tool_calls (ToolStrategy mode)
        structured_response = self._extract_structured_response(messages)

        # 2. Fallback to result structured_response (ProviderStrategy/ToolStrategy native mode)
        if structured_response is None:
            raw_structured = result.get("structured_response")
            if raw_structured is not None:
                if hasattr(raw_structured, "model_dump"):
                    structured_response = raw_structured.model_dump()
                elif isinstance(raw_structured, dict):
                    structured_response = raw_structured

        # 3. Fallback to parsing the last message content as JSON
        if structured_response is None:
            structured_response = self._try_parse_json(last_message.content)

        # 4. Validate against response_format schema (strip extra fields)
        if structured_response is not None and self._response_format_model is not None:
            structured_response = self._validate_structured_response(structured_response)

        return Message(
            role=MessageRole.AI,
            content=last_message.content,
            tool_calls=all_tool_calls or None,
            status=status,
            structured_response=structured_response,
            thinking=thinking,
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
            response = self._build_response(result, config, None)
            logger.info("[thread=%s] Invoke complete, status=%s, elapsed=%.2fs", thread_id, response.status, elapsed)
            return response
        except Exception as e:
            logger.exception("[thread=%s] Agent execution error", thread_id)
            raise AgentError(f"Agent execution error: {e}") from e

    async def _yield_chunks(
        self, thread_id: str, message: str, config: dict, stats: dict
    ) -> AsyncIterator[StreamEvent]:
        start = time.monotonic()
        first_chunk = True
        chunk_count = 0
        async for chunk, _metadata in self._graph.astream(
            {"messages": [{"role": "human", "content": message}]},
            config=config,
            stream_mode="messages",
        ):
            classification = self._classify_chunk(chunk)
            if classification:
                event_type, data = classification
                if first_chunk:
                    logger.info("[thread=%s] First chunk received, elapsed=%.2fs", thread_id, time.monotonic() - start)
                    first_chunk = False
                chunk_count += 1
                yield StreamEvent(type=event_type, data=data)
        stats["chunk_count"] = chunk_count
        stats["elapsed"] = time.monotonic() - start

    async def stream(self, thread_id: str, message: str) -> AsyncIterator[StreamEvent]:
        config = self._build_config(thread_id)
        logger.info("[thread=%s] Streaming agent response", thread_id)
        try:
            stats: dict = {}
            async for event in self._yield_chunks(thread_id, message, config, stats):
                yield event
            logger.info(
                "[thread=%s] Stream complete, %d chunks, elapsed=%.2fs",
                thread_id,
                stats["chunk_count"],
                stats["elapsed"],
            )
        except Exception as e:
            logger.exception("[thread=%s] Streaming error", thread_id)
            raise AgentError(f"Streaming error: {e}") from e

    async def stream_with_message(self, thread_id: str, message: str) -> AsyncIterator[StreamEvent]:
        config = self._build_config(thread_id)
        logger.info("[thread=%s] Streaming agent response with final message", thread_id)
        try:
            stats: dict = {}
            thinking_parts = []
            async for event in self._yield_chunks(thread_id, message, config, stats):
                yield event
                if event.type == StreamEventType.THINKING:
                    thinking_parts.append(event.data)
            state = self._graph.get_state(config)
            values = getattr(state, "values", None) or {}
            result = {"messages": values.get("messages", []), "structured_response": values.get("structured_response")}
            thinking = "".join(thinking_parts) if thinking_parts else None
            response = self._build_response(result, config, thinking)
            logger.info(
                "[thread=%s] Stream with message complete, %d chunks, elapsed=%.2fs, status=%s",
                thread_id,
                stats["chunk_count"],
                stats["elapsed"],
                response.status,
            )
            yield StreamEvent(type=StreamEventType.MESSAGE, data=response.model_dump_json())
        except Exception as e:
            logger.exception("[thread=%s] Streaming error", thread_id)
            raise AgentError(f"Streaming error: {e}") from e

    async def approve_hitl(self, thread_id: str, _tool_call_id: str) -> Message:
        config = self._build_config(thread_id)
        logger.info("[thread=%s] HITL approve", thread_id)
        try:
            start = time.monotonic()
            result = await self._graph.ainvoke(Command(resume={"decisions": [{"type": "approve"}]}), config=config)
            elapsed = time.monotonic() - start
            response = self._build_response(result, config, None)
            logger.info("[thread=%s] HITL approve complete, elapsed=%.2fs", thread_id, elapsed)
            return response
        except Exception as e:
            logger.exception("HITL approve error")
            raise AgentError(f"HITL approve error: {e}") from e

    async def reject_hitl(self, thread_id: str, _tool_call_id: str, reason: str | None = None) -> Message:
        config = self._build_config(thread_id)
        logger.info("[thread=%s] HITL reject, reason=%s", thread_id, reason)
        try:
            start = time.monotonic()
            result = await self._graph.ainvoke(
                Command(resume={"decisions": [{"type": "reject", "message": reason or ""}]}), config=config
            )
            elapsed = time.monotonic() - start
            response = self._build_response(result, config, None)
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
            tool_name = next(
                (
                    tc["name"]
                    for msg in state.values.get("messages", [])
                    if hasattr(msg, "tool_calls")
                    for tc in msg.tool_calls
                    if tc.get("id") == tool_call_id
                ),
                tool_call_id,
            )
            result = await self._graph.ainvoke(
                Command(resume={"decisions": [{"type": "edit", "edited_action": {"name": tool_name, "args": edits}}]}),
                config=config,
            )
            elapsed = time.monotonic() - start
            response = self._build_response(result, config, None)
            logger.info("[thread=%s] HITL edit complete, elapsed=%.2fs", thread_id, elapsed)
            return response
        except Exception as e:
            logger.exception("HITL edit error")
            raise AgentError(f"HITL edit error: {e}") from e
