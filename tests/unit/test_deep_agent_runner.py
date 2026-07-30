"""Tests for DeepAgentRunner (HITL refactor — TDD red phase).

The runner is the SUT (internal) and is instantiated for real.
The LangGraph CompiledStateGraph is an external boundary and is mocked with
MagicMock/AsyncMock. Tests exercise only public methods (invoke, stream,
resume_hitl).

The default checkpointer becomes Postgres (async-only), so the runner now
reads state via ``await self._graph.aget_state(config)`` instead of the
synchronous ``get_state``.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.entities.hitl_decision import HitlDecision
from src.domain.entities.message import MessageRole, MessageStatus
from src.domain.entities.trace_event import TraceEventType
from src.domain.errors.agent import AgentError
from src.infrastructure.deepagent.adapter import DeepAgentRunner
from src.infrastructure.deepagent.schema_utils import schema_to_pydantic_model


def _make_graph(messages, interrupts=(), state_values=None):
    """Create a mock graph with astream (empty) and aget_state.

    The runner uses ``await self._graph.aget_state(config)`` to read the final
    state. We make ``astream`` yield nothing so the runner falls back to
    reading the final state from ``aget_state``. Both ``aget_state`` and the
    legacy sync ``get_state`` are provided.
    """
    mock_graph = AsyncMock()
    state = MagicMock()
    state.interrupts = interrupts
    state.values = state_values or {"messages": messages}
    mock_graph.aget_state = AsyncMock(return_value=state)
    mock_graph.get_state = MagicMock(return_value=state)
    mock_graph.nodes = {}

    async def _empty_astream(_input, **_kwargs):
        return
        yield  # noqa: F841 — makes this an async generator

    mock_graph.astream = _empty_astream
    mock_graph.ainvoke.return_value = {"messages": messages}
    return mock_graph


def _make_msg(content="Hello", tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    return msg


class TestInvoke:
    async def test_invoke_returns_ai_message(self):
        # Arrange
        graph = _make_graph([_make_msg("Hello from agent")])

        # Act
        runner = DeepAgentRunner(graph)
        result, trace = await runner.invoke("thread-1", "Hello", "turn-1")

        # Assert
        assert result.role == MessageRole.AI
        assert result.content == "Hello from agent"
        assert result.status == MessageStatus.COMPLETED

    async def test_invoke_uses_only_last_message_tool_calls(self):
        # Arrange
        human = MagicMock(spec=[])
        human.type = "human"
        ai_with_tools = _make_msg(tool_calls=[{"name": "word_count", "args": {"text": "hello"}, "id": "tc-1"}])
        tool_msg = MagicMock(spec=[])
        final_ai = _make_msg("The text has 1 word.", tool_calls=[])
        graph = _make_graph([human, ai_with_tools, tool_msg, final_ai])

        # Act
        runner = DeepAgentRunner(graph)
        result, trace = await runner.invoke("thread-1", "count words in hello", "turn-1")

        # Assert
        assert result.content == "The text has 1 word."
        assert result.tool_calls is None

    async def test_invoke_detects_hitl_interruption(self):
        # Arrange
        ai_msg = _make_msg("", tool_calls=[{"name": "word_count", "args": {"text": "hi"}, "id": "tc-1"}])
        interrupt = MagicMock()
        graph = _make_graph([ai_msg], interrupts=(interrupt,))

        # Act
        runner = DeepAgentRunner(graph)
        result, trace = await runner.invoke("thread-1", "count words", "turn-1")

        # Assert
        assert result.status == MessageStatus.AWAITING_HITL
        assert result.tool_calls is not None

    async def test_invoke_completed_when_no_interrupts(self):
        # Arrange
        graph = _make_graph([_make_msg("Done")], interrupts=())

        # Act
        runner = DeepAgentRunner(graph)
        result, trace = await runner.invoke("thread-1", "Hello", "turn-1")

        # Assert
        assert result.status == MessageStatus.COMPLETED

    async def test_invoke_returns_none_tool_calls_when_last_message_empty(self):
        # Arrange
        old_human = MagicMock(spec=[])
        old_human.type = "human"
        old_ai = _make_msg(tool_calls=[{"name": "old_tool", "args": {}, "id": "tc-old"}])
        new_human = MagicMock(spec=[])
        new_human.type = "human"
        final_ai = _make_msg("New response", tool_calls=[])
        graph = _make_graph([old_human, old_ai, new_human, final_ai])

        # Act
        runner = DeepAgentRunner(graph)
        result, trace = await runner.invoke("thread-1", "new question", "turn-1")

        # Assert
        assert result.content == "New response"
        assert result.tool_calls is None

    async def test_invoke_raises_agent_error_on_graph_failure(self):
        # Arrange
        graph = AsyncMock()
        graph.ainvoke.side_effect = RuntimeError("LLM error")
        graph.nodes = {}

        # Act & Assert
        runner = DeepAgentRunner(graph)
        with pytest.raises(AgentError, match="Agent execution error"):
            await runner.invoke("thread-1", "Hello", "turn-1")


class TestInvokeStructuredResponse:
    async def test_invoke_extracts_structured_response_dict(self):
        # Arrange
        msg = _make_msg("Weather report")
        graph = _make_graph(
            [msg], state_values={"messages": [msg], "structured_response": {"temperature": 22, "condition": "sunny"}}
        )

        # Act
        runner = DeepAgentRunner(graph)
        result, trace = await runner.invoke("thread-1", "weather?", "turn-1")

        # Assert
        assert result.structured_response == {"temperature": 22, "condition": "sunny"}

    async def test_invoke_extracts_structured_response_via_model_dump(self):
        # Arrange
        msg = _make_msg("Report")
        pydantic_obj = MagicMock()
        pydantic_obj.model_dump.return_value = {"temperature": 15, "condition": "cloudy"}
        graph = _make_graph([msg], state_values={"messages": [msg], "structured_response": pydantic_obj})

        # Act
        runner = DeepAgentRunner(graph)
        result, trace = await runner.invoke("thread-1", "weather?", "turn-1")

        # Assert
        assert result.structured_response == {"temperature": 15, "condition": "cloudy"}

    async def test_invoke_no_structured_response_returns_none(self):
        # Arrange
        graph = _make_graph([_make_msg("Hello")])

        # Act
        runner = DeepAgentRunner(graph)
        result, trace = await runner.invoke("thread-1", "hi", "turn-1")

        # Assert
        assert result.structured_response is None

    async def test_invoke_validates_and_strips_extra_top_level_fields(self):
        # Arrange

        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name"],
        }
        model = schema_to_pydantic_model(schema)
        msg = _make_msg("Result")
        graph = _make_graph(
            [msg],
            state_values={
                "messages": [msg],
                "structured_response": {"name": "Alice", "age": 30, "terraceArea": 50, "parkingSpaces": 2},
            },
        )

        # Act
        runner = DeepAgentRunner(graph, response_format_model=model)
        result, trace = await runner.invoke("thread-1", "analyze", "turn-1")

        # Assert
        assert result.structured_response == {"name": "Alice", "age": 30}

    async def test_invoke_validates_and_strips_nested_extra_fields(self):
        # Arrange

        schema = {
            "type": "object",
            "properties": {
                "building": {
                    "type": "object",
                    "properties": {"floors": {"type": "integer"}},
                    "required": ["floors"],
                }
            },
            "required": ["building"],
        }
        model = schema_to_pydantic_model(schema)
        msg = _make_msg("Result")
        graph = _make_graph(
            [msg], state_values={"messages": [msg], "structured_response": {"building": {"floors": 3, "rooftop": True}}}
        )

        # Act
        runner = DeepAgentRunner(graph, response_format_model=model)
        result, trace = await runner.invoke("thread-1", "analyze", "turn-1")

        # Assert
        assert result.structured_response == {"building": {"floors": 3}}

    async def test_invoke_no_response_format_model_passes_raw(self):
        # Arrange
        msg = _make_msg("Result")
        graph = _make_graph(
            [msg], state_values={"messages": [msg], "structured_response": {"name": "test", "extra": True}}
        )

        # Act
        runner = DeepAgentRunner(graph, response_format_model=None)
        result, trace = await runner.invoke("thread-1", "analyze", "turn-1")

        # Assert
        assert result.structured_response == {"name": "test", "extra": True}

    async def test_invoke_validates_structured_response_from_tool_call(self):
        # Arrange

        schema = {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        }
        model = schema_to_pydantic_model(schema)
        ai_msg = _make_msg(
            "Done",
            tool_calls=[{"name": "structured_response", "args": {"summary": "ok", "hallucinated": 99}, "id": "tc-1"}],
        )
        graph = _make_graph(
            [ai_msg],
            state_values={"messages": [ai_msg], "structured_response": {"summary": "ok", "hallucinated": 99}},
        )

        # Act
        runner = DeepAgentRunner(graph, response_format_model=model)
        result, trace = await runner.invoke("thread-1", "summarize", "turn-1")

        # Assert
        assert result.structured_response == {"summary": "ok"}


class TestInvokeTimeout:
    async def test_invoke_timeout_raises_agent_error(self):
        # Arrange
        graph = AsyncMock()
        graph.nodes = {}

        async def _astream_hang(_input, **_kwargs):
            yield ("", MagicMock())
            await asyncio.sleep(10)

        graph.astream = _astream_hang

        # Act & Assert
        runner = DeepAgentRunner(graph, stream_idle_timeout=0.05)
        with pytest.raises(AgentError, match="stream idle"):
            await runner.invoke("thread-1", "hello", "turn-1")


class TestStream:
    async def test_stream_yields_content_events(self):
        # Arrange
        graph = AsyncMock()
        graph.nodes = {}

        async def _astream(_input, **_kwargs):
            chunk = _make_msg("chunk")
            chunk.type = "AIMessageChunk"
            chunk.additional_kwargs = {}
            chunk.tool_call_chunks = None
            yield (chunk, MagicMock())

        graph.astream = _astream
        state = MagicMock(values={"messages": [_make_msg("chunk")]}, interrupts=())
        graph.aget_state = AsyncMock(return_value=state)
        graph.get_state = MagicMock(return_value=state)

        # Act
        runner = DeepAgentRunner(graph)
        events = [e async for e in runner.stream("thread-1", "Hi", "turn-1")]

        # Assert: HUMAN + CONTENT + AI_MESSAGE = 3
        assert len(events) == 3
        content_events = [e for e in events if e.type == TraceEventType.CONTENT]
        assert len(content_events) == 1
        assert content_events[0].content == "chunk"


# --------------------------------------------------------------------------- #
# NEW resume_hitl contract (replaces approve/reject/edit_hitl)
# --------------------------------------------------------------------------- #


def _resume_graph(
    tool_calls,
    action_requests,
    interrupt_present=True,
    final_messages=None,
    post_interrupt_present=None,
):
    """Build a mock graph for resume_hitl tests.

    Args:
        tool_calls: list of dicts for the last AI message's tool_calls
            (each with ``name``, ``args``, ``id``) — the interrupted AI message.
        action_requests: list of ActionRequest-like dicts (``{name, args,
            description?}``) — the interrupt payload, positional, matching the
            AI message's tool_calls order (filtered by interrupt_on config).
        interrupt_present: whether the FIRST ``aget_state().interrupts`` is
            non-empty (pre-resume check — drives the "nothing to resume" guard).
        final_messages: messages exposed through the POST-resume ``aget_state``.
            defaults to the AI message holding ``tool_calls``.
        post_interrupt_present: whether the POST-resume ``aget_state().interrupts``
            is non-empty. Defaults to ``interrupt_present``. Use this to model a
            subsequent interrupt (True) or clean completion (False) after resume.
    """
    ai_msg = _make_msg("", tool_calls=tool_calls)
    pre_messages = [ai_msg]
    post_messages = final_messages if final_messages is not None else [ai_msg]

    pre_interrupt = MagicMock() if interrupt_present else None
    pre_interrupts = (pre_interrupt,) if interrupt_present else ()
    if interrupt_present:
        pre_interrupt.value = {
            "action_requests": action_requests,
            "review_configs": [],
        }

    if post_interrupt_present is None:
        post_interrupt_present = interrupt_present
    post_interrupts = (MagicMock(),) if post_interrupt_present else ()

    graph = AsyncMock()
    graph.nodes = {}

    pre_state = MagicMock()
    pre_state.interrupts = pre_interrupts
    pre_state.values = {"messages": pre_messages}

    post_state = MagicMock()
    post_state.interrupts = post_interrupts
    post_state.values = {"messages": post_messages}

    # First aget_state call returns the pre-resume state; every subsequent
    # call returns the post-resume state (used to build the final AI_MESSAGE).
    call_count = {"n": 0}

    async def _aget_state(_config):
        call_count["n"] += 1
        return pre_state if call_count["n"] == 1 else post_state

    graph.aget_state = _aget_state
    graph.get_state = MagicMock(return_value=post_state)

    return graph, ai_msg


def _capture_astream_input(graph):
    """Replace ``graph.astream`` with a spy that records the input and yields nothing."""
    captured: dict = {}

    async def _spy_astream(_input, **_kwargs):
        captured["input"] = _input
        return
        yield  # noqa: F841 — async generator marker

    graph.astream = _spy_astream
    return captured


class TestResumeHitl:
    async def test_resume_hitl_returns_message_and_trace(self):
        # Arrange — single interrupt, approve
        graph, _ = _resume_graph(
            tool_calls=[{"name": "search", "args": {"q": "x"}, "id": "tc-1"}],
            action_requests=[{"name": "search", "args": {"q": "x"}, "description": "search"}],
            interrupt_present=True,
        )
        runner = DeepAgentRunner(graph)

        # Act
        message, trace = await runner.resume_hitl(
            "thread-1", [HitlDecision(tool_call_id="tc-1", action="approve")], "turn-1"
        )

        # Assert
        assert message is not None
        assert message.status == MessageStatus.COMPLETED
        assert isinstance(trace, list)
        assert len(trace) >= 1
        assert trace[0].type == TraceEventType.HITL_DECISION
        assert trace[0].name == "approve"
        assert trace[-1].type == TraceEventType.AI_MESSAGE

    async def test_resume_hitl_completed_when_no_interrupts(self):
        # Arrange — pre-resume interrupt present (something to resume), but no
        # further interrupt after resume → status COMPLETED.
        graph, _ = _resume_graph(
            tool_calls=[{"name": "search", "args": {"q": "x"}, "id": "tc-1"}],
            action_requests=[{"name": "search", "args": {"q": "x"}, "description": "search"}],
            interrupt_present=True,
            final_messages=[_make_msg("Search complete.", tool_calls=[])],
            post_interrupt_present=False,
        )
        runner = DeepAgentRunner(graph)

        # Act
        message, trace = await runner.resume_hitl(
            "thread-1", [HitlDecision(tool_call_id="tc-1", action="approve")], "turn-1"
        )

        # Assert
        assert message.status == MessageStatus.COMPLETED

    async def test_resume_hitl_detects_subsequent_interrupt(self):
        # Arrange — pre-resume interrupt on tc-1 (search); after resume a new
        # interrupt appears (deploy) → AWAITING_HITL.
        graph, _ = _resume_graph(
            tool_calls=[{"name": "search", "args": {"q": "x"}, "id": "tc-1"}],
            action_requests=[{"name": "search", "args": {"q": "x"}, "description": "search"}],
            interrupt_present=True,
            final_messages=[_make_msg("", tool_calls=[{"name": "deploy", "args": {}, "id": "tc-2"}])],
            post_interrupt_present=True,
        )
        runner = DeepAgentRunner(graph)

        # Act
        message, trace = await runner.resume_hitl(
            "thread-1", [HitlDecision(tool_call_id="tc-1", action="approve")], "turn-1"
        )

        # Assert
        assert message.status == MessageStatus.AWAITING_HITL

    async def test_resume_hitl_raises_when_no_pending_interrupt(self):
        # Arrange — aget_state.interrupts is empty AND no action_requests:
        # nothing to resume (clears the cryptic 500 on double-click).
        graph = AsyncMock()
        graph.nodes = {}
        state = MagicMock()
        state.interrupts = ()
        state.values = {"messages": [_make_msg("Done.", tool_calls=[])]}
        graph.aget_state = AsyncMock(return_value=state)
        graph.get_state = MagicMock(return_value=state)
        runner = DeepAgentRunner(graph)

        # Act & Assert
        with pytest.raises(AgentError, match="no pending|nothing to resume"):
            await runner.resume_hitl("thread-1", [HitlDecision(tool_call_id="tc-1", action="approve")], "turn-1")

    async def test_resume_hitl_reject_passes_reason(self):
        # Arrange — reject decision must carry the reason as ``message``.
        graph, _ = _resume_graph(
            tool_calls=[{"name": "search", "args": {"q": "x"}, "id": "tc-1"}],
            action_requests=[{"name": "search", "args": {"q": "x"}, "description": "search"}],
            interrupt_present=True,
        )
        captured = _capture_astream_input(graph)
        runner = DeepAgentRunner(graph)

        # Act
        await runner.resume_hitl(
            "thread-1",
            [HitlDecision(tool_call_id="tc-1", action="reject", reason="not safe")],
            "turn-1",
        )

        # Assert — the resume payload contains the reject decision with message
        input_cmd = captured["input"]
        resume = getattr(input_cmd, "resume", None)
        assert resume is not None
        decisions = resume["decisions"]
        assert decisions == [{"type": "reject", "message": "not safe"}]

    async def test_resume_hitl_multi_decisions_positional(self):
        # Arrange — two interrupted tool calls; decisions must be positional
        # and match the order of action_requests.
        graph, _ = _resume_graph(
            tool_calls=[
                {"name": "delete", "args": {}, "id": "tc-a"},
                {"name": "write", "args": {}, "id": "tc-b"},
            ],
            action_requests=[
                {"name": "delete", "args": {}, "description": "delete"},
                {"name": "write", "args": {}, "description": "write"},
            ],
            interrupt_present=True,
        )
        captured = _capture_astream_input(graph)
        runner = DeepAgentRunner(graph)

        # Act
        await runner.resume_hitl(
            "thread-1",
            [
                HitlDecision(tool_call_id="tc-a", action="approve"),
                HitlDecision(tool_call_id="tc-b", action="reject", reason="no"),
            ],
            "turn-1",
        )

        # Assert — positional decisions in action_requests order
        resume = getattr(captured["input"], "resume", None)
        assert resume is not None
        decisions = resume["decisions"]
        assert decisions == [{"type": "approve"}, {"type": "reject", "message": "no"}]

    async def test_resume_hitl_unknown_tool_call_id_raises(self):
        # Arrange — decisions reference a tool_call_id not in the interrupted
        # action_requests.
        graph, _ = _resume_graph(
            tool_calls=[{"name": "search", "args": {"q": "x"}, "id": "tc-1"}],
            action_requests=[{"name": "search", "args": {"q": "x"}, "description": "search"}],
            interrupt_present=True,
        )
        runner = DeepAgentRunner(graph)

        # Act & Assert
        with pytest.raises(AgentError, match="unknown|not found"):
            await runner.resume_hitl(
                "thread-1",
                [HitlDecision(tool_call_id="tc-unknown", action="approve")],
                "turn-1",
            )

    async def test_resume_hitl_missing_decision_raises(self):
        # Arrange — only 1 decision provided but 2 action_requests pending.
        graph, _ = _resume_graph(
            tool_calls=[
                {"name": "delete", "args": {}, "id": "tc-a"},
                {"name": "write", "args": {}, "id": "tc-b"},
            ],
            action_requests=[
                {"name": "delete", "args": {}, "description": "delete"},
                {"name": "write", "args": {}, "description": "write"},
            ],
            interrupt_present=True,
        )
        runner = DeepAgentRunner(graph)

        # Act & Assert
        with pytest.raises(AgentError, match="missing|mismatch"):
            await runner.resume_hitl(
                "thread-1",
                [HitlDecision(tool_call_id="tc-a", action="approve")],
                "turn-1",
            )

    async def test_resume_hitl_edit_passes_edited_action(self):
        # Arrange — edit decision must resolve the tool name from the last AI
        # message tool_calls and build an ``edited_action`` payload.
        graph, _ = _resume_graph(
            tool_calls=[{"name": "send_email", "args": {"to": "a@b.com"}, "id": "tc-1"}],
            action_requests=[{"name": "send_email", "args": {"to": "a@b.com"}, "description": "send"}],
            interrupt_present=True,
        )
        captured = _capture_astream_input(graph)
        runner = DeepAgentRunner(graph)

        # Act
        await runner.resume_hitl(
            "thread-1",
            [HitlDecision(tool_call_id="tc-1", action="edit", edits={"k": "v"})],
            "turn-1",
        )

        # Assert — edited_action carries the resolved tool name + edited args
        resume = getattr(captured["input"], "resume", None)
        assert resume is not None
        decisions = resume["decisions"]
        assert decisions == [{"type": "edit", "edited_action": {"name": "send_email", "args": {"k": "v"}}}]
