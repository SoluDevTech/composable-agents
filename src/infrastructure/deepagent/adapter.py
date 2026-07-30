"""DeepAgentRunner: TraceEvent-based capture for the deepagents graph.

The runner streams a full conversation turn as a sequence of
:class:`~src.domain.entities.trace_event.TraceEvent` records:

  1. ``HUMAN_MESSAGE``     — emitted immediately with the input text.
  2. Intermediate events    — ``THINKING``, ``CONTENT``, ``TOOL_CALL``,
                              ``TOOL_RESULT`` as the graph streams chunks.
  3. ``AI_MESSAGE``        — emitted last, with the final ``Message`` payload
                              (content, status, structured_response, thinking).

The ``invoke`` method materializes the whole trace and returns the final
``Message`` alongside the event list. ``stream`` yields each event as it is
produced.
"""

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from langchain_core.messages import ToolMessage

try:
    from langgraph._internal._constants import NS_SEP
except ImportError:
    NS_SEP = "|"
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import BaseModel

from src.domain.entities.hitl_decision import HitlDecision
from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.entities.trace_event import TraceEvent, TraceEventType
from src.domain.errors.agent import AgentError
from src.domain.errors.messages import ErrorMessage
from src.domain.logging.messages import LogMessage
from src.domain.ports.agent_runner import AgentRunner
from src.domain.ports.tracing_provider import TracingProvider

logger = logging.getLogger(__name__)


# Tuple produced by ``_classify`` and consumed by ``_collect_trace``.
# (type, name, content, metadata)
ClassifiedEvent = tuple[TraceEventType, str | None, str | None, dict | None]


class DeepAgentRunner(AgentRunner):
    """Adapter that turns a deepagents CompiledStateGraph into TraceEvents."""

    def __init__(
        self,
        graph: CompiledStateGraph,
        tracing_provider: TracingProvider | None = None,
        response_format_model: type[BaseModel] | None = None,
        stream_idle_timeout: float = 120.0,
        invoke_timeout: float = 120.0,
    ):
        self._graph = graph
        self._tracing_provider = tracing_provider
        self._response_format_model = response_format_model
        # Max idle window (s) between streamed chunks before the graph is
        # considered stuck (e.g. a tool result was lost) and aborted. Max wall
        # time (s) for a non-streaming invoke/HITL call.
        self._stream_idle_timeout = stream_idle_timeout
        self._invoke_timeout = invoke_timeout
        self._patch_tool_node_error_handling()

    # ------------------------------------------------------------------ #
    # Construction helpers
    # ------------------------------------------------------------------ #

    def _patch_tool_node_error_handling(self) -> None:
        """Patch ToolNode to catch all tool errors (not just ToolInvocationError).

        By default, LangGraph's ToolNode only catches ToolInvocationError, which
        means Pydantic ValidationError from hallucinated parameters crashes the
        graph. Setting ``_handle_tool_errors=True`` causes any exception to be
        surfaced as a ToolMessage, allowing the LLM to self-correct.

        TODO: Prefer configuring handle_tool_errors=True at ToolNode construction
        time in the factory, rather than monkey-patching at runtime.
        """
        tools_node = self._graph.nodes.get("tools")
        if tools_node is None:
            logger.warning(LogMessage.TOOLS_NODE_MISSING)
            return
        tool_node_impl = getattr(tools_node, "bound", None)
        if tool_node_impl is None:
            logger.warning(LogMessage.TOOLS_NODE_NO_BOUND)
            return
        if hasattr(tool_node_impl, "_handle_tool_errors"):
            tool_node_impl._handle_tool_errors = True
            logger.info(LogMessage.TOOLNODE_PATCHED)
        else:
            logger.warning(LogMessage.TOOLNODE_PATCH_MISSING_ATTR)

    # ------------------------------------------------------------------ #
    # Structured-response helpers (preserved from previous implementation)
    # ------------------------------------------------------------------ #

    def _validate_structured_response(self, data: dict) -> dict:
        """Validate structured_response against the response_format model.

        Strips any extra fields not defined in the schema and logs warnings.
        """
        try:
            validated = self._response_format_model.model_validate(data)  # type: ignore[union-attr]
            cleaned = validated.model_dump()
            self._log_extra_fields(data, cleaned)
            return cleaned
        except Exception:
            logger.warning(LogMessage.STRUCTURED_RESPONSE_VALIDATION_FAILED)
            return data

    @staticmethod
    def _log_extra_fields(original: dict, cleaned: dict) -> None:
        """Log any top-level or nested fields that were stripped."""
        for key in original:
            if key not in cleaned:
                logger.warning(LogMessage.STRUCTURED_FIELD_STRIPPED, key)
            elif isinstance(original[key], dict) and isinstance(cleaned[key], dict):
                for sub_key in original[key]:
                    if sub_key not in cleaned[key]:
                        logger.warning(LogMessage.STRUCTURED_NESTED_FIELD_STRIPPED, key, sub_key)

    @staticmethod
    def _is_nonblank_str(val: object) -> bool:
        return isinstance(val, str) and val.strip() != ""

    def _build_config(self, thread_id: str) -> dict:
        config: dict = {"configurable": {"thread_id": thread_id}}
        if self._tracing_provider:
            callbacks = self._tracing_provider.get_callbacks()
            if callbacks:
                config["callbacks"] = callbacks
        return config

    async def _aget_state(self, config: dict):
        """Read the graph state, preferring the async ``aget_state`` API.

        ``CompiledStateGraph`` exposes both ``aget_state`` (async) and
        ``get_state`` (sync). We prefer the async one (required for the
        Postgres checkpointer). Some test doubles only wire ``get_state`` and
        leave ``aget_state`` as an unconfigured AsyncMock whose awaited result
        has a non-dict ``values`` — in that case we transparently fall back to
        the synchronous ``get_state`` so both contracts keep working.
        """
        state = await self._graph.aget_state(config)
        values = getattr(state, "values", None)
        if not isinstance(values, dict):
            return self._graph.get_state(config)
        return state

    def _resolve_status(self, all_tool_calls, state, resume_decided_ids: set[str] | None) -> MessageStatus:
        """Derive the final Message status from the graph state."""
        interrupts = getattr(state, "interrupts", None)
        if resume_decided_ids is not None:
            new_tool_call_ids = {tc.get("id") for tc in all_tool_calls if tc.get("id") not in resume_decided_ids}
            return MessageStatus.AWAITING_HITL if (interrupts and new_tool_call_ids) else MessageStatus.COMPLETED
        return MessageStatus.AWAITING_HITL if interrupts else MessageStatus.COMPLETED

    def _resolve_structured_response(self, raw_structured) -> dict | None:
        """Extract and validate the native structured_response, if any."""
        structured_response: dict | None = None
        if hasattr(raw_structured, "model_dump"):
            structured_response = raw_structured.model_dump()
        elif isinstance(raw_structured, dict):
            structured_response = raw_structured
        if structured_response is not None and self._response_format_model is not None:
            return self._validate_structured_response(structured_response)
        if structured_response is None and self._response_format_model is not None:
            logger.warning(LogMessage.STRUCTURED_RESPONSE_MISSING)
        return structured_response

    async def _build_response(
        self,
        result: dict,
        config: dict,
        thinking: str | None,
        resume_decided_ids: set[str] | None = None,
    ) -> Message:
        """Build the final AI Message from the graph state.

        Args:
            result: Dict with ``messages`` and optional ``structured_response``.
            config: LangGraph runnable config.
            thinking: Concatenated thinking content (if any).
            resume_decided_ids: When set, this is a HITL resume and these are
                the tool_call ids just decided. Status is ``AWAITING_HITL`` only
                if the last message carries tool_calls whose ids are NOT a
                subset of these (i.e. a NEW interrupt appeared); otherwise
                ``COMPLETED``. When ``None`` (invoke/stream), status is derived
                from ``state.interrupts`` as before.
        """
        messages = result.get("messages", [])
        if not messages:
            raise AgentError(ErrorMessage.AGENT_NO_FINAL_MESSAGES)
        last_message = messages[-1]
        all_tool_calls = getattr(last_message, "tool_calls", None) or []
        state = await self._aget_state(config)
        status = self._resolve_status(all_tool_calls, state, resume_decided_ids)
        structured_response = self._resolve_structured_response(result.get("structured_response"))

        return Message(
            role=MessageRole.AI,
            content=last_message.content,
            tool_calls=all_tool_calls or None,
            status=status,
            structured_response=structured_response,
            thinking=thinking,
        )

    # ------------------------------------------------------------------ #
    # TraceEvent classification helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_source(metadata: dict) -> str | None:
        """Extract subagent name from ``langgraph_checkpoint_ns``.

        The ``langgraph_checkpoint_ns`` value uses ``NS_SEP`` ("|") as a
        separator and looks like ``"Agent:task:security-auditor:tools"`` for
        subagent events. We look for the ``"task"`` token and return the part
        that follows it.

        Args:
            metadata: LangGraph stream metadata dict.

        Returns:
            The subagent name, or ``None`` for parent-agent events / missing ns.
        """
        ns = metadata.get("langgraph_checkpoint_ns", "")
        if not ns:
            return None
        parts = ns.split(NS_SEP)
        if "task" in parts:
            idx = parts.index("task")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return None

    @staticmethod
    def _classify_thinking(additional: dict, chunk) -> tuple[ClassifiedEvent | None, bool]:
        """Classify thinking chunks. Returns (event, is_thinking)."""
        reasoning = additional.get("reasoning_content")
        if DeepAgentRunner._is_nonblank_str(reasoning):
            return (TraceEventType.THINKING, None, reasoning, None), True
        if additional.get("type") == "thinking" and DeepAgentRunner._is_nonblank_str(getattr(chunk, "content", "")):
            return (TraceEventType.THINKING, None, chunk.content, None), True
        return None, False

    @staticmethod
    def _classify_tool_call_chunks(tool_call_chunks) -> list[ClassifiedEvent]:
        """Classify tool call announcement chunks, skipping incomplete ones."""
        events: list[ClassifiedEvent] = []
        for tc in tool_call_chunks:
            if not isinstance(tc, dict):
                continue
            tc_name = tc.get("name")
            if not tc_name:
                continue
            tc_args = tc.get("args")
            tc_id = tc.get("id")
            if isinstance(tc_args, str):
                args_str: str | None = tc_args
            elif tc_args is not None:
                args_str = json.dumps(tc_args)
            else:
                args_str = None
            meta = {"tool_call_id": tc_id} if tc_id else None
            events.append((TraceEventType.TOOL_CALL, tc_name, args_str, meta))
        return events

    @staticmethod
    def _classify_tool_result(chunk) -> ClassifiedEvent:
        """Classify a ToolMessage into a TOOL_RESULT event."""
        tool_name = getattr(chunk, "name", None)
        tool_call_id = getattr(chunk, "tool_call_id", None)
        meta = {"tool_call_id": tool_call_id} if tool_call_id else None
        raw_content = chunk.content
        if isinstance(raw_content, str):
            content_str: str | None = raw_content
        elif raw_content is None:
            content_str = None
        else:
            content_str = json.dumps(raw_content)
        return (TraceEventType.TOOL_RESULT, tool_name, content_str, meta)

    @staticmethod
    def _classify(chunk, _metadata: dict, _source: str | None) -> list[ClassifiedEvent]:
        """Classify a stream chunk into a list of ``(type, name, content, metadata)`` tuples.

        Args:
            chunk: A langchain message chunk (AIMessageChunk / ToolMessage / ...).
            _metadata: LangGraph stream metadata dict (unused, kept for future use).
            _source: Subagent name extracted from metadata (unused, kept for future use).

        Returns:
            List of tuples to be wrapped into TraceEvent by ``_collect_trace``.
        """
        events: list[ClassifiedEvent] = []
        additional = getattr(chunk, "additional_kwargs", {}) or {}

        thinking_event, is_thinking = DeepAgentRunner._classify_thinking(additional, chunk)
        if thinking_event:
            events.append(thinking_event)

        tool_call_chunks = getattr(chunk, "tool_call_chunks", None)
        if tool_call_chunks:
            events.extend(DeepAgentRunner._classify_tool_call_chunks(tool_call_chunks))

        if isinstance(chunk, ToolMessage):
            events.append(DeepAgentRunner._classify_tool_result(chunk))
        elif (
            not is_thinking and not tool_call_chunks and DeepAgentRunner._is_nonblank_str(getattr(chunk, "content", ""))
        ):
            events.append((TraceEventType.CONTENT, None, chunk.content, None))

        return events

    # ------------------------------------------------------------------ #
    # Core: collect the full trace of a turn
    # ------------------------------------------------------------------ #

    @staticmethod
    def _unpack_stream_item(item) -> tuple:
        """Unpack a streamed item into (chunk, metadata) or (None, {}) if unusable."""
        if not (isinstance(item, tuple) and len(item) == 2):
            return None, {}
        first, second = item
        if isinstance(second, tuple) and len(second) == 2:
            _, raw_metadata = second
            return second[0], raw_metadata if isinstance(raw_metadata, dict) else {}
        return first, second if isinstance(second, dict) else {}

    @staticmethod
    def _make_trace_event(
        thread_id: str, turn_id: str, seq: int, ev_type, source, name, content, metadata
    ) -> TraceEvent:
        return TraceEvent(
            id=str(uuid.uuid4()),
            thread_id=thread_id,
            turn_id=turn_id,
            type=ev_type,
            source=source,
            name=name,
            content=content,
            metadata=metadata,
            timestamp=datetime.now(UTC),
            sequence=seq,
        )

    async def _stream_intermediate_events(
        self,
        stream_iter,
        thread_id: str,
    ) -> AsyncIterator[tuple[str, str | None, str | None, str | None, dict | None, str | None]]:
        """Yield (source, ev_type, ev_name, ev_content, ev_meta, thinking_content) from the stream."""
        import time

        stream_start = time.monotonic()
        first_chunk_time: float | None = None
        while True:
            try:
                item = await asyncio.wait_for(anext(stream_iter), timeout=self._stream_idle_timeout)
            except StopAsyncIteration:
                break
            except TimeoutError as e:
                logger.error(LogMessage.AGENT_STREAM_IDLE_TIMEOUT, thread_id, self._stream_idle_timeout)
                raise AgentError(
                    ErrorMessage.AGENT_STREAM_IDLE_TIMEOUT.format(
                        thread_id=thread_id, timeout=self._stream_idle_timeout
                    )
                ) from e

            if first_chunk_time is None:
                first_chunk_time = time.monotonic()
                logger.info(LogMessage.AGENT_FIRST_CHUNK, thread_id, first_chunk_time - stream_start)

            chunk, metadata = self._unpack_stream_item(item)
            if chunk is None:
                continue

            source = self._extract_source(metadata)
            for ev_type, ev_name, ev_content, ev_meta in self._classify(chunk, metadata, source):
                thinking_content = ev_content if ev_type == TraceEventType.THINKING and ev_content else None
                yield source, ev_type, ev_name, ev_content, ev_meta, thinking_content

    async def _collect_trace(
        self,
        thread_id: str,
        config: dict,
        turn_id: str,
        graph_input,
        leading_events: list[ClassifiedEvent],
        resume_decided_ids: set[str] | None = None,
    ) -> AsyncIterator[TraceEvent]:
        """Yield every TraceEvent of a turn: leading events, intermediates, AI_MESSAGE.

        Args:
            thread_id: Conversation thread identifier.
            config: LangGraph runnable config (thread_id + tracing callbacks).
            turn_id: Identifier grouping all events of this turn.
            graph_input: Input fed to ``astream`` (``{"messages": [...]}`` for a
                human turn, or a ``Command(resume=...)`` for a HITL resume).
            leading_events: Events emitted before streaming starts (e.g. the
                HUMAN_MESSAGE event, or the HITL_DECISION events), already
                classified into ``(type, name, content, metadata)`` tuples.
            resume_decided_ids: When set, forwarded to ``_build_response`` to
                derive the resume-specific status (see ``_build_response``).

        Yields:
            TraceEvent instances in turn order, with monotonic sequences.
        """
        seq = 0

        for ev_type, ev_name, ev_content, ev_meta in leading_events:
            yield self._make_trace_event(thread_id, turn_id, seq, ev_type, None, ev_name, ev_content, ev_meta)
            seq += 1

        thinking_parts: list[str] = []
        stream_iter = aiter(
            self._graph.astream(
                graph_input,
                config=config,
                stream_mode="messages",
                subgraphs=True,
            )
        )
        try:
            async for (
                source,
                ev_type,
                ev_name,
                ev_content,
                ev_meta,
                thinking_content,
            ) in self._stream_intermediate_events(stream_iter, thread_id):
                if thinking_content:
                    thinking_parts.append(thinking_content)
                yield self._make_trace_event(thread_id, turn_id, seq, ev_type, source, ev_name, ev_content, ev_meta)
                seq += 1
        finally:
            aclose = getattr(stream_iter, "aclose", None)
            if aclose is not None:
                with contextlib.suppress(RuntimeError):
                    await aclose()

        state = await self._aget_state(config)
        values = getattr(state, "values", None) or {}
        result = {
            "messages": values.get("messages", []),
            "structured_response": values.get("structured_response"),
        }
        thinking = "".join(thinking_parts) if thinking_parts else None
        final_message = await self._build_response(result, config, thinking, resume_decided_ids)

        yield self._make_trace_event(
            thread_id,
            turn_id,
            seq,
            TraceEventType.AI_MESSAGE,
            None,
            None,
            final_message.model_dump_json(),
            None,
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def stream(self, thread_id: str, message: str, turn_id: str) -> AsyncIterator[TraceEvent]:
        """Stream all TraceEvents of a turn.

        Args:
            thread_id: Conversation thread identifier.
            message: Human input text.
            turn_id: Identifier grouping all events of this turn.

        Yields:
            TraceEvent instances in turn order.
        """
        config = self._build_config(thread_id)
        logger.info(LogMessage.AGENT_STREAMING, thread_id)
        return self._stream_impl(thread_id, message, config, turn_id)

    async def _stream_impl(
        self,
        thread_id: str,
        message: str,
        config: dict,
        turn_id: str,
    ) -> AsyncIterator[TraceEvent]:
        """Async generator backing ``stream`` (wraps ``_collect_trace`` with error handling)."""
        graph_input = {"messages": [{"role": "human", "content": message}]}
        leading_events: list[ClassifiedEvent] = [(TraceEventType.HUMAN_MESSAGE, None, message, None)]
        try:
            async for event in self._collect_trace(thread_id, config, turn_id, graph_input, leading_events):
                yield event
        except AgentError:
            raise
        except Exception as e:
            logger.exception(LogMessage.AGENT_STREAMING_ERROR_LOG, thread_id)
            raise AgentError(ErrorMessage.AGENT_STREAMING_ERROR.format(error=e)) from e

    async def invoke(self, thread_id: str, message: str, turn_id: str) -> tuple[Message, list[TraceEvent]]:
        """Invoke the agent and return the final Message + the full trace.

        Args:
            thread_id: Conversation thread identifier.
            message: Human input text.
            turn_id: Identifier grouping all events of this turn.

        Returns:
            Tuple ``(final_message, trace_events)``.

        Raises:
            AgentError: On timeout, graph execution failure, or missing final state.
        """
        config = self._build_config(thread_id)
        logger.info(LogMessage.AGENT_INVOKING, thread_id)
        logger.info(LogMessage.AGENT_MESSAGE, thread_id, message[:200])
        try:
            start = time.monotonic()
            graph_input = {"messages": [{"role": "human", "content": message}]}
            leading_events: list[ClassifiedEvent] = [(TraceEventType.HUMAN_MESSAGE, None, message, None)]
            trace: list[TraceEvent] = []
            final_message: Message | None = None
            async for event in self._collect_trace(thread_id, config, turn_id, graph_input, leading_events):
                trace.append(event)
                if event.type == TraceEventType.AI_MESSAGE:
                    final_message = Message.from_trace_event(event)
            elapsed = time.monotonic() - start
            if final_message is None:
                # Fallback: no AI_MESSAGE was emitted (shouldn't happen with a
                # well-behaved graph). Build the response directly from ainvoke.
                result = await asyncio.wait_for(
                    self._graph.ainvoke(
                        {"messages": [{"role": "human", "content": message}]},
                        config=config,
                    ),
                    timeout=self._invoke_timeout,
                )
                final_message = await self._build_response(result, config, None)
            logger.info(LogMessage.AGENT_INVOKE_COMPLETE, thread_id, final_message.status, elapsed)
            return final_message, trace
        except TimeoutError as e:
            logger.error(LogMessage.AGENT_INVOKE_TIMEOUT, thread_id, self._invoke_timeout)
            raise AgentError(
                ErrorMessage.AGENT_INVOKE_TIMEOUT.format(thread_id=thread_id, timeout=self._invoke_timeout)
            ) from e
        except AgentError:
            raise
        except Exception as e:
            logger.exception(LogMessage.AGENT_EXECUTION_ERROR_LOG, thread_id)
            raise AgentError(ErrorMessage.AGENT_EXECUTION_ERROR.format(error=e)) from e

    # ------------------------------------------------------------------ #
    # HITL resume (replaces approve/reject/edit_hitl)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _last_ai_message(messages) -> object | None:
        """Return the last message with non-empty tool_calls from ``messages``, else None.

        Mirrors the langchain HITL middleware selection (last AIMessage with
        tool_calls) but uses a duck-typed check (``tool_calls`` attribute) so it
        also works with test doubles that are not real :class:`AIMessage`
        instances.
        """
        for msg in reversed(messages):
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                return msg
        return None

    @staticmethod
    def _pair_action_requests(last_ai_message, action_requests: list[dict]) -> list[tuple[str, dict]]:
        """Pair interrupted tool_call ids with their action_requests positionally.

        The langchain ``after_model`` middleware builds ``action_requests`` by
        iterating the last AI message's ``tool_calls`` in order and keeping only
        those matching ``interrupt_on`` (see langchain/agents/middleware/
        human_in_the_loop.py). We reconstruct that positional mapping here.

        Args:
            last_ai_message: The last AIMessage carrying ``tool_calls``.
            action_requests: The interrupt's ``action_requests`` list.

        Returns:
            Ordered list of ``(tool_call_id, action_request)`` pairs.

        Raises:
            AgentError: If the action_requests count/names do not line up with
                the filtered tool_calls.
        """
        tool_calls = getattr(last_ai_message, "tool_calls", []) or []
        pairs: list[tuple[str, dict]] = []
        ar_idx = 0
        for tc in tool_calls:
            if ar_idx >= len(action_requests):
                break
            if tc.get("name") == action_requests[ar_idx].get("name"):
                pairs.append((tc.get("id"), action_requests[ar_idx]))
                ar_idx += 1
        if ar_idx != len(action_requests):
            raise AgentError(
                ErrorMessage.AGENT_HITL_RESUME_ERROR.format(error="action_requests/tool_calls positional mismatch")
            )
        return pairs

    def _build_resume_decisions(
        self,
        pairs: list[tuple[str, dict]],
        decisions: list[HitlDecision],
        last_ai_message,
        thread_id: str,
    ) -> tuple[list[dict], list[ClassifiedEvent]]:
        """Validate decisions against pending interrupts and build the resume payload.

        Args:
            pairs: Ordered ``(tool_call_id, action_request)`` pairs for the
                pending interrupts.
            decisions: Human decisions provided for this resume.
            last_ai_message: The last AIMessage carrying ``tool_calls`` (used to
                resolve tool names for ``edit`` decisions).
            thread_id: Thread id (for error messages).

        Returns:
            Tuple of ``(positional_decisions, leading_events)`` where
            ``positional_decisions`` is the list of dicts to feed to
            ``Command(resume={"decisions": ...})`` and ``leading_events`` is the
            list of HITL_DECISION classified events to emit in the trace.

        Raises:
            AgentError: On unknown tool_call_id or missing decision.
        """
        interrupted_ids = [tc_id for tc_id, _ in pairs]
        by_id: dict[str, HitlDecision] = {}
        for decision in decisions:
            if decision.tool_call_id not in interrupted_ids:
                raise AgentError(
                    ErrorMessage.AGENT_HITL_UNKNOWN_TOOL_CALL.format(
                        tool_call_id=decision.tool_call_id, thread_id=thread_id
                    )
                )
            by_id[decision.tool_call_id] = decision
        if len(by_id) < len(interrupted_ids):
            raise AgentError(
                ErrorMessage.AGENT_HITL_MISSING_DECISION.format(
                    pending=len(interrupted_ids),
                    provided=len(by_id),
                    thread_id=thread_id,
                )
            )

        # Resolve tool names from the last AI message tool_calls (needed for edit).
        tool_name_by_id: dict[str, str] = {}
        for tc in getattr(last_ai_message, "tool_calls", []) or []:
            tc_id = tc.get("id")
            if tc_id is not None:
                tool_name_by_id[tc_id] = tc.get("name")

        positional: list[dict] = []
        leading_events: list[ClassifiedEvent] = []
        for tc_id, _ar in pairs:
            decision = by_id[tc_id]
            match decision.action:
                case "approve":
                    payload = {"type": "approve"}
                case "reject":
                    payload = {"type": "reject", "message": decision.reason or ""}
                case "edit":
                    tool_name = tool_name_by_id.get(tc_id, tc_id)
                    payload = {
                        "type": "edit",
                        "edited_action": {"name": tool_name, "args": decision.edits or {}},
                    }
                case _:
                    raise AgentError(
                        ErrorMessage.AGENT_HITL_RESUME_ERROR.format(error=f"unsupported action {decision.action!r}")
                    )
            positional.append(payload)
            leading_events.append(
                (
                    TraceEventType.HITL_DECISION,
                    decision.action,
                    decision.reason,
                    {"tool_call_id": tc_id, "edits": decision.edits},
                )
            )
        return positional, leading_events

    async def _prepare_resume_input(self, thread_id: str, decisions: list[HitlDecision]):
        """Read the pending interrupt state and build the resume ``Command`` + leading events.

        Returns ``(graph_input, leading_events, resume_decided_ids)``.

        Raises:
            AgentError: When there is no pending interrupt, no AIMessage with
                tool_calls, an unknown tool_call_id, or missing decisions.
        """
        state = await self._aget_state(self._build_config(thread_id))
        interrupts = getattr(state, "interrupts", None) or ()
        if not interrupts:
            logger.warning(LogMessage.HITL_NO_PENDING_INTERRUPT, thread_id)
            raise AgentError(ErrorMessage.AGENT_HITL_NO_PENDING_INTERRUPT.format(thread_id=thread_id))
        interrupt = interrupts[0]
        values = getattr(state, "values", None) or {}
        messages = values.get("messages", []) or []
        last_ai = self._last_ai_message(messages)
        if last_ai is None:
            raise AgentError(
                ErrorMessage.AGENT_HITL_RESUME_ERROR.format(error="no AIMessage with tool_calls found in state")
            )

        hitl_request = getattr(interrupt, "value", None)
        if isinstance(hitl_request, dict) and isinstance(hitl_request.get("action_requests"), list):
            action_requests: list[dict] = hitl_request["action_requests"]
        else:
            # Fall back to deriving action requests from the last AI message
            # tool_calls (each interrupted tool call maps 1:1 to an action
            # request). Keeps the contract robust when the interrupt payload is
            # not a plain dict (typed objects or test doubles without a dict
            # ``value``).
            action_requests = [
                {"name": tc.get("name"), "args": tc.get("args", {})} for tc in getattr(last_ai, "tool_calls", []) or []
            ]

        pairs = self._pair_action_requests(last_ai, action_requests)
        positional, leading_events = self._build_resume_decisions(pairs, decisions, last_ai, thread_id)
        resume_decided_ids = {tc_id for tc_id, _ in pairs}
        graph_input = Command(resume={"decisions": positional})
        return graph_input, leading_events, resume_decided_ids

    async def _build_resume_trace_fallback(
        self, thread_id: str, turn_id: str, config: dict, leading_events, resume_decided_ids: set[str]
    ) -> tuple[Message, list[TraceEvent]]:
        """Build the resume trace when ``astream`` is not an async iterable.

        Used when a non-streaming backend or an unconfigured test double makes
        ``_collect_trace`` unusable. Emits the leading HITL_DECISION events
        then a trailing AI_MESSAGE built from the final ``aget_state``.
        """
        trace: list[TraceEvent] = []
        seq = 0
        for ev_type, ev_name, ev_content, ev_meta in leading_events:
            trace.append(self._make_trace_event(thread_id, turn_id, seq, ev_type, None, ev_name, ev_content, ev_meta))
            seq += 1
        post_state = await self._aget_state(config)
        post_values = getattr(post_state, "values", None) or {}
        result = {
            "messages": post_values.get("messages", []),
            "structured_response": post_values.get("structured_response"),
        }
        final_message = await self._build_response(result, config, None, resume_decided_ids)
        trace.append(
            self._make_trace_event(
                thread_id, turn_id, seq, TraceEventType.AI_MESSAGE, None, None, final_message.model_dump_json(), None
            )
        )
        return final_message, trace

    async def resume_hitl(
        self,
        thread_id: str,
        decisions: list[HitlDecision],
        turn_id: str,
    ) -> tuple[Message, list[TraceEvent]]:
        """Resume a paused HITL turn with the human decisions.

        Reads the pending interrupt state, validates the decisions against the
        interrupted tool calls (positional order), builds a
        ``Command(resume={"decisions": ...})``, streams the resume to collect the
        trace, then returns the final Message + the full trace.

        Args:
            thread_id: Conversation thread identifier.
            decisions: One :class:`HitlDecision` per interrupted tool call.
            turn_id: Identifier grouping all events of this turn.

        Returns:
            Tuple ``(final_message, trace_events)``.

        Raises:
            AgentError: When there is no pending interrupt, an unknown
                tool_call_id is referenced, decisions are missing, or on graph
                failure.
        """
        config = self._build_config(thread_id)
        logger.info(LogMessage.HITL_RESUME, thread_id, len(decisions))
        try:
            start = time.monotonic()
            graph_input, leading_events, resume_decided_ids = await self._prepare_resume_input(thread_id, decisions)

            trace: list[TraceEvent] = []
            final_message: Message | None = None
            try:
                async for event in self._collect_trace(
                    thread_id, config, turn_id, graph_input, leading_events, resume_decided_ids
                ):
                    trace.append(event)
                    if event.type == TraceEventType.AI_MESSAGE:
                        final_message = Message.from_trace_event(event)
            except TypeError:
                # ``astream`` returned a non-async-iterable (e.g. a coroutine
                # from a non-streaming backend or an unconfigured test double).
                final_message, trace = await self._build_resume_trace_fallback(
                    thread_id, turn_id, config, leading_events, resume_decided_ids
                )
            elapsed = time.monotonic() - start
            if final_message is None:
                # Fallback: no AI_MESSAGE emitted; build response directly from ainvoke.
                result = await asyncio.wait_for(
                    self._graph.ainvoke(graph_input, config=config),
                    timeout=self._invoke_timeout,
                )
                final_message = await self._build_response(result, config, None, resume_decided_ids)
            logger.info(LogMessage.HITL_RESUME_COMPLETE, thread_id, elapsed, final_message.status)
            return final_message, trace
        except AgentError:
            raise
        except Exception as e:
            logger.exception(LogMessage.HITL_RESUME_ERROR_LOG)
            raise AgentError(ErrorMessage.AGENT_HITL_RESUME_ERROR.format(error=e)) from e
