"""Tests for DeepAgentRunner.stream_with_message.

The runner is the SUT (internal) and is instantiated for real.
The LangGraph CompiledStateGraph is an external boundary and is mocked.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.entities.stream_event import StreamEventType
from src.domain.errors.agent import AgentError
from src.infrastructure.deepagent.adapter import DeepAgentRunner


def _make_streaming_graph(
    chunks: list[tuple[StreamEventType, str]],
    final_messages: list | None = None,
    interrupts=(),
    state_values: dict | None = None,
    structured_response=None,
):
    mock_graph = AsyncMock()
    mock_graph.nodes = {}

    async def _astream(_input, **_kwargs):
        for event_type, chunk_text in chunks:
            chunk = MagicMock()
            chunk.content = chunk_text
            chunk.type = "AIMessageChunk"
            chunk.additional_kwargs = {}
            if event_type == StreamEventType.THINKING:
                chunk.additional_kwargs = {"type": "thinking"}
            yield chunk, MagicMock()

    mock_graph.astream = _astream
    state = MagicMock()
    state.interrupts = interrupts

    if final_messages is None:
        content = "".join(text for etype, text in chunks if etype == StreamEventType.CONTENT)
        final_ai = MagicMock()
        final_ai.content = content
        final_ai.tool_calls = None
        final_messages = [final_ai]

    values = state_values or {}
    if "messages" not in values:
        values["messages"] = final_messages
    if structured_response is not None:
        values["structured_response"] = structured_response
    state.values = values

    mock_graph.get_state = MagicMock(return_value=state)
    mock_graph.ainvoke.return_value = {
        "messages": final_messages,
        "structured_response": structured_response,
    }
    return mock_graph


class TestStreamWithMessage:
    async def test_yields_content_events_then_final_message(self):
        # Arrange
        chunks = [(StreamEventType.CONTENT, "Hello "), (StreamEventType.CONTENT, "world!")]
        graph = _make_streaming_graph(chunks)

        # Act
        runner = DeepAgentRunner(graph)
        collected = [event async for event in runner.stream_with_message("thread-1", "hi")]

        # Assert
        content_events = collected[:-1]
        assert all(e.type == StreamEventType.CONTENT for e in content_events)
        assert [e.data for e in content_events] == ["Hello ", "world!"]
        final_event = collected[-1]
        assert final_event.type == StreamEventType.MESSAGE
        msg = Message.model_validate_json(final_event.data)
        assert msg.role == MessageRole.AI
        assert msg.content == "Hello world!"
        assert msg.status == MessageStatus.COMPLETED

    async def test_yields_thinking_then_content(self):
        # Arrange
        chunks = [
            (StreamEventType.THINKING, "Let me think..."),
            (StreamEventType.CONTENT, "Here is the answer."),
        ]
        graph = _make_streaming_graph(chunks)

        # Act
        runner = DeepAgentRunner(graph)
        collected = [event async for event in runner.stream_with_message("thread-1", "hi")]

        # Assert
        events = collected[:-1]
        assert events[0].type == StreamEventType.THINKING
        assert events[0].data == "Let me think..."
        assert events[1].type == StreamEventType.CONTENT
        assert events[1].data == "Here is the answer."
        msg = Message.model_validate_json(collected[-1].data)
        assert msg.thinking == "Let me think..."
        assert msg.content == "Here is the answer."

    async def test_final_message_has_tool_calls(self):
        # Arrange
        chunks = [(StreamEventType.CONTENT, "Processing...")]
        ai_msg = MagicMock()
        ai_msg.content = "Processing..."
        ai_msg.tool_calls = [{"name": "search", "args": {"q": "test"}, "id": "tc-1"}]
        graph = _make_streaming_graph(chunks, final_messages=[ai_msg])

        # Act
        runner = DeepAgentRunner(graph)
        collected = [event async for event in runner.stream_with_message("thread-1", "search for test")]

        # Assert
        msg = Message.model_validate_json(collected[-1].data)
        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0]["name"] == "search"

    async def test_final_message_has_structured_response(self):
        # Arrange
        chunks = [(StreamEventType.CONTENT, "Weather report")]
        ai_msg = MagicMock()
        ai_msg.content = "Weather report"
        ai_msg.tool_calls = None
        graph = _make_streaming_graph(
            chunks,
            final_messages=[ai_msg],
            structured_response={"temperature": 22, "condition": "sunny"},
        )

        # Act
        runner = DeepAgentRunner(graph)
        collected = [event async for event in runner.stream_with_message("thread-1", "weather?")]

        # Assert
        msg = Message.model_validate_json(collected[-1].data)
        assert msg.structured_response == {"temperature": 22, "condition": "sunny"}

    async def test_detects_hitl_interrupt(self):
        # Arrange
        chunks = [(StreamEventType.CONTENT, "Waiting for approval")]
        ai_msg = MagicMock()
        ai_msg.content = ""
        ai_msg.tool_calls = [{"name": "delete_file", "args": {"path": "/tmp/x"}, "id": "tc-1"}]
        interrupt = MagicMock()
        graph = _make_streaming_graph(chunks, final_messages=[ai_msg], interrupts=(interrupt,))

        # Act
        runner = DeepAgentRunner(graph)
        collected = [event async for event in runner.stream_with_message("thread-1", "delete file")]

        # Assert
        msg = Message.model_validate_json(collected[-1].data)
        assert msg.status == MessageStatus.AWAITING_HITL

    async def test_no_chunks_yields_only_message(self):
        # Arrange
        graph = _make_streaming_graph([])

        # Act
        runner = DeepAgentRunner(graph)
        collected = [event async for event in runner.stream_with_message("thread-1", "hello")]

        # Assert
        assert len(collected) == 1
        assert collected[0].type == StreamEventType.MESSAGE
        msg = Message.model_validate_json(collected[0].data)
        assert msg.role == MessageRole.AI

    async def test_raises_agent_error_on_graph_failure(self):
        # Arrange
        graph = AsyncMock()
        graph.nodes = {}

        async def _astream_error(_input, _config=None, _stream_mode=None):
            raise RuntimeError("LLM streaming error")

        graph.astream = _astream_error

        # Act & Assert
        runner = DeepAgentRunner(graph)
        with pytest.raises(AgentError, match="Streaming error"):
            async for _event in runner.stream_with_message("thread-1", "hello"):
                pass

    async def test_idle_timeout_raises_agent_error(self):
        # Arrange
        graph = AsyncMock()
        graph.nodes = {}

        async def _astream_hang(_input, **_kwargs):
            chunk = MagicMock()
            chunk.content = "first"
            chunk.type = "AIMessageChunk"
            chunk.additional_kwargs = {}
            yield chunk, MagicMock()
            await asyncio.sleep(10)

        graph.astream = _astream_hang

        # Act & Assert
        runner = DeepAgentRunner(graph, stream_idle_timeout=0.05)
        with pytest.raises(AgentError, match="idle"):
            async for _event in runner.stream_with_message("thread-1", "hello"):
                pass
