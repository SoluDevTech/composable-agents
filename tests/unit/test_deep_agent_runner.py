"""Tests for DeepAgentRunner.

The runner is the SUT (internal) and is instantiated for real.
The LangGraph CompiledStateGraph is an external boundary and is mocked with
MagicMock/AsyncMock. Tests exercise only public methods (invoke, stream,
stream_with_message, approve_hitl, reject_hitl, edit_hitl).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.entities.message import MessageRole, MessageStatus
from src.domain.entities.stream_event import StreamEventType
from src.domain.errors.agent import AgentError
from src.infrastructure.deepagent.adapter import DeepAgentRunner
from src.infrastructure.deepagent.schema_utils import make_validation_model


def _make_graph(messages, interrupts=(), state_values=None):
    """Create a mock graph with ainvoke result and get_state."""
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {"messages": messages}
    state = MagicMock()
    state.interrupts = interrupts
    state.values = state_values or {}
    mock_graph.get_state = MagicMock(return_value=state)
    mock_graph.nodes = {}
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
        result = await runner.invoke("thread-1", "Hello")

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
        result = await runner.invoke("thread-1", "count words in hello")

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
        result = await runner.invoke("thread-1", "count words")

        # Assert
        assert result.status == MessageStatus.AWAITING_HITL
        assert result.tool_calls is not None

    async def test_invoke_completed_when_no_interrupts(self):
        # Arrange
        graph = _make_graph([_make_msg("Done")], interrupts=())

        # Act
        runner = DeepAgentRunner(graph)
        result = await runner.invoke("thread-1", "Hello")

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
        result = await runner.invoke("thread-1", "new question")

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
            await runner.invoke("thread-1", "Hello")


class TestInvokeStructuredResponse:
    async def test_invoke_extracts_structured_response_dict(self):
        # Arrange
        msg = _make_msg("Weather report")
        graph = _make_graph([msg])
        graph.ainvoke.return_value = {
            "messages": [msg],
            "structured_response": {"temperature": 22, "condition": "sunny"},
        }

        # Act
        runner = DeepAgentRunner(graph)
        result = await runner.invoke("thread-1", "weather?")

        # Assert
        assert result.structured_response == {"temperature": 22, "condition": "sunny"}

    async def test_invoke_extracts_structured_response_via_model_dump(self):
        # Arrange
        msg = _make_msg("Report")
        pydantic_obj = MagicMock()
        pydantic_obj.model_dump.return_value = {"temperature": 15, "condition": "cloudy"}
        graph = _make_graph([msg])
        graph.ainvoke.return_value = {
            "messages": [msg],
            "structured_response": pydantic_obj,
        }

        # Act
        runner = DeepAgentRunner(graph)
        result = await runner.invoke("thread-1", "weather?")

        # Assert
        assert result.structured_response == {"temperature": 15, "condition": "cloudy"}

    async def test_invoke_no_structured_response_returns_none(self):
        # Arrange
        graph = _make_graph([_make_msg("Hello")])

        # Act
        runner = DeepAgentRunner(graph)
        result = await runner.invoke("thread-1", "hi")

        # Assert
        assert result.structured_response is None

    async def test_invoke_validates_and_strips_extra_top_level_fields(self):
        # Arrange

        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name"],
        }
        model = make_validation_model(schema)
        msg = _make_msg("Result")
        graph = _make_graph([msg])
        graph.ainvoke.return_value = {
            "messages": [msg],
            "structured_response": {"name": "Alice", "age": 30, "terraceArea": 50, "parkingSpaces": 2},
        }

        # Act
        runner = DeepAgentRunner(graph, response_format_model=model)
        result = await runner.invoke("thread-1", "analyze")

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
        model = make_validation_model(schema)
        msg = _make_msg("Result")
        graph = _make_graph([msg])
        graph.ainvoke.return_value = {
            "messages": [msg],
            "structured_response": {"building": {"floors": 3, "rooftop": True}},
        }

        # Act
        runner = DeepAgentRunner(graph, response_format_model=model)
        result = await runner.invoke("thread-1", "analyze")

        # Assert
        assert result.structured_response == {"building": {"floors": 3}}

    async def test_invoke_no_response_format_model_passes_raw(self):
        # Arrange
        msg = _make_msg("Result")
        graph = _make_graph([msg])
        graph.ainvoke.return_value = {
            "messages": [msg],
            "structured_response": {"name": "test", "extra": True},
        }

        # Act
        runner = DeepAgentRunner(graph, response_format_model=None)
        result = await runner.invoke("thread-1", "analyze")

        # Assert
        assert result.structured_response == {"name": "test", "extra": True}

    async def test_invoke_validates_structured_response_from_tool_call(self):
        # Arrange

        schema = {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        }
        model = make_validation_model(schema)
        ai_msg = _make_msg(
            "Done",
            tool_calls=[{"name": "structured_response", "args": {"summary": "ok", "hallucinated": 99}, "id": "tc-1"}],
        )
        graph = _make_graph([ai_msg])

        # Act
        runner = DeepAgentRunner(graph, response_format_model=model)
        result = await runner.invoke("thread-1", "summarize")

        # Assert
        assert result.structured_response == {"summary": "ok"}


class TestApproveHitl:
    async def test_approve_detects_subsequent_interrupt(self):
        # Arrange
        human = MagicMock(spec=[])
        human.type = "human"
        ai_with_tools = _make_msg(tool_calls=[{"name": "search", "args": {"q": "test"}, "id": "tc-2"}])
        tool_result = MagicMock(spec=[])
        final_ai = _make_msg("", tool_calls=[{"name": "deploy", "args": {}, "id": "tc-3"}])
        interrupt = MagicMock()
        graph = _make_graph(
            [human, ai_with_tools, tool_result, final_ai],
            interrupts=(interrupt,),
        )

        # Act
        runner = DeepAgentRunner(graph)
        result = await runner.approve_hitl("thread-1", "tc-1")

        # Assert
        assert result.status == MessageStatus.AWAITING_HITL
        assert any(tc["name"] == "deploy" for tc in result.tool_calls)

    async def test_approve_completed_when_no_interrupts(self):
        # Arrange
        human = MagicMock(spec=[])
        human.type = "human"
        ai_with_tools = _make_msg(tool_calls=[{"name": "search", "args": {"q": "test"}, "id": "tc-10"}])
        tool_result = MagicMock(spec=[])
        final_ai = _make_msg("Search complete. Found 3 results.", tool_calls=[])
        graph = _make_graph([human, ai_with_tools, tool_result, final_ai], interrupts=())

        # Act
        runner = DeepAgentRunner(graph)
        result = await runner.approve_hitl("thread-1", "tc-1")

        # Assert
        assert result.status == MessageStatus.COMPLETED
        assert result.content == "Search complete. Found 3 results."
        assert result.tool_calls is None


class TestRejectHitl:
    async def test_reject_detects_subsequent_interrupt(self):
        # Arrange
        human = MagicMock(spec=[])
        human.type = "human"
        ai_with_tools = _make_msg(tool_calls=[{"name": "delete_file", "args": {"path": "/tmp"}, "id": "tc-5"}])
        tool_result = MagicMock(spec=[])
        final_ai = _make_msg("", tool_calls=[{"name": "confirm_delete", "args": {}, "id": "tc-6"}])
        interrupt = MagicMock()
        graph = _make_graph(
            [human, ai_with_tools, tool_result, final_ai],
            interrupts=(interrupt,),
        )

        # Act
        runner = DeepAgentRunner(graph)
        result = await runner.reject_hitl("thread-1", "tc-4", reason="not safe")

        # Assert
        assert result.status == MessageStatus.AWAITING_HITL
        assert any(tc["name"] == "confirm_delete" for tc in result.tool_calls)

    async def test_reject_completed_when_no_interrupts(self):
        # Arrange
        human = MagicMock(spec=[])
        human.type = "human"
        ai_with_tools = _make_msg(tool_calls=[{"name": "word_count", "args": {"text": "test"}, "id": "tc-1"}])
        final_ai = _make_msg("I can count manually: 1 word.", tool_calls=[])
        graph = _make_graph([human, ai_with_tools, final_ai], interrupts=())

        # Act
        runner = DeepAgentRunner(graph)
        result = await runner.reject_hitl("thread-1", "tc-1", reason="not allowed")

        # Assert
        assert result.status == MessageStatus.COMPLETED
        assert result.content == "I can count manually: 1 word."
        assert result.tool_calls is None


class TestEditHitl:
    async def test_edit_detects_subsequent_interrupt(self):
        # Arrange
        human = MagicMock(spec=[])
        human.type = "human"
        ai_with_tools = _make_msg(tool_calls=[{"name": "send_email", "args": {"to": "a@b.com"}, "id": "tc-8"}])
        tool_result = MagicMock(spec=[])
        final_ai = _make_msg("", tool_calls=[{"name": "confirm_send", "args": {}, "id": "tc-9"}])
        interrupt = MagicMock()
        state_msg = _make_msg(tool_calls=[{"name": "send_email", "args": {"to": "a@b.com"}, "id": "tc-7"}])
        graph = _make_graph(
            [human, ai_with_tools, tool_result, final_ai],
            interrupts=(interrupt,),
            state_values={"messages": [state_msg]},
        )

        # Act
        runner = DeepAgentRunner(graph)
        result = await runner.edit_hitl("thread-1", "tc-7", edits={"to": "x@y.com"})

        # Assert
        assert result.status == MessageStatus.AWAITING_HITL
        assert any(tc["name"] == "confirm_send" for tc in result.tool_calls)


class TestInvokeTimeout:
    async def test_invoke_timeout_raises_agent_error(self):
        # Arrange
        graph = AsyncMock()
        graph.nodes = {}

        async def _ainvoke_hang(_input, **_kwargs):
            await asyncio.sleep(10)
            return {"messages": []}

        graph.ainvoke = _ainvoke_hang

        # Act & Assert
        runner = DeepAgentRunner(graph, invoke_timeout=0.05)
        with pytest.raises(AgentError, match="timed out"):
            await runner.invoke("thread-1", "hello")


class TestStream:
    async def test_stream_yields_content_events(self):
        # Arrange
        graph = AsyncMock()
        graph.nodes = {}

        async def _astream(_input, **_kwargs):
            chunk = _make_msg("chunk")
            chunk.type = "AIMessageChunk"
            chunk.additional_kwargs = {}
            yield (chunk, MagicMock())

        graph.astream = _astream
        graph.get_state = MagicMock(
            return_value=MagicMock(values={"messages": [_make_msg("chunk")]}, interrupts=())
        )

        # Act
        runner = DeepAgentRunner(graph)
        events = [e async for e in runner.stream("thread-1", "Hi")]

        # Assert
        assert len(events) == 1
        assert events[0].type == StreamEventType.CONTENT
        assert events[0].data == "chunk"
