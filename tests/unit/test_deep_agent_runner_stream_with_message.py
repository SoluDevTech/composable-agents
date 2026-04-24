"""Tests for DeepAgentRunner.stream_with_message().

Graph is mocked (external LLM boundary via LangGraph).
These tests exercise the new stream_with_message() method which yields
str chunks during streaming and a final Message object after the stream
completes, allowing callers to receive both streaming chunks and a
structured complete response.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.exceptions import AgentError
from src.infrastructure.deepagent.adapter import DeepAgentRunner


def _make_streaming_graph(
    chunks: list[str],
    final_messages: list | None = None,
    interrupts=(),
    state_values: dict | None = None,
    structured_response=None,
):
    """Create a mock graph with astream and get_state for stream_with_message.

    Args:
        chunks: List of string chunks to yield from astream.
        final_messages: Messages to appear in get_state().values["messages"].
            If None, a default AI message is constructed from the chunks.
        interrupts: Interrupt tuples for get_state().
        state_values: Additional state values for get_state().
        structured_response: Optional structured_response value in state.
    """
    mock_graph = AsyncMock()

    # Build async generator for astream
    async def _astream(_input, **_kwargs):
        for chunk_text in chunks:
            chunk = MagicMock()
            chunk.content = chunk_text
            chunk.type = "AIMessageChunk"
            yield chunk, MagicMock()

    mock_graph.astream = _astream

    # Build state for get_state (called after stream to build Message)
    state = MagicMock()
    state.interrupts = interrupts

    # Build final AI message from joined chunks if no explicit messages given
    if final_messages is None:
        final_ai = MagicMock()
        final_ai.content = "".join(chunks)
        final_ai.tool_calls = None
        final_messages = [final_ai]

    values = state_values or {}
    if "messages" not in values:
        values["messages"] = final_messages
    if structured_response is not None:
        values["structured_response"] = structured_response
    state.values = values

    mock_graph.get_state = MagicMock(return_value=state)

    # ainvoke return value (used by get_state context)
    mock_graph.ainvoke.return_value = {
        "messages": final_messages,
        "structured_response": structured_response,
    }

    return mock_graph


class TestStreamWithMessage:
    """Tests for DeepAgentRunner.stream_with_message()."""

    async def test_stream_with_message_yields_chunks_then_message(self):
        """Should yield str chunks during streaming, then a final Message."""
        chunks = ["Hello ", "world!"]
        graph = _make_streaming_graph(chunks)

        runner = DeepAgentRunner(graph)
        collected = []
        async for item in runner.stream_with_message("thread-1", "hi"):
            collected.append(item)

        # All items except the last should be str chunks
        str_items = collected[:-1]
        final_message = collected[-1]

        assert all(isinstance(c, str) for c in str_items)
        assert str_items == ["Hello ", "world!"]

        assert isinstance(final_message, Message)
        assert final_message.role == MessageRole.AI
        assert final_message.content == "Hello world!"
        assert final_message.status == MessageStatus.COMPLETED

    async def test_stream_with_message_final_message_has_tool_calls(self):
        """When the last message has tool_calls, the final Message includes them."""
        chunks = ["Processing..."]

        ai_msg = MagicMock()
        ai_msg.content = "Processing..."
        ai_msg.tool_calls = [{"name": "search", "args": {"q": "test"}, "id": "tc-1"}]

        graph = _make_streaming_graph(
            chunks,
            final_messages=[ai_msg],
            structured_response=None,
        )

        runner = DeepAgentRunner(graph)
        collected = []
        async for item in runner.stream_with_message("thread-1", "search for test"):
            collected.append(item)

        final_message = collected[-1]
        assert isinstance(final_message, Message)
        assert final_message.tool_calls is not None
        assert len(final_message.tool_calls) == 1
        assert final_message.tool_calls[0]["name"] == "search"

    async def test_stream_with_message_final_message_has_structured_response(self):
        """When result has structured_response, it appears in the final Message."""
        chunks = ["Weather report"]

        ai_msg = MagicMock()
        ai_msg.content = "Weather report"
        ai_msg.tool_calls = None

        graph = _make_streaming_graph(
            chunks,
            final_messages=[ai_msg],
            structured_response={"temperature": 22, "condition": "sunny"},
        )

        runner = DeepAgentRunner(graph)
        collected = []
        async for item in runner.stream_with_message("thread-1", "weather?"):
            collected.append(item)

        final_message = collected[-1]
        assert isinstance(final_message, Message)
        assert final_message.structured_response == {"temperature": 22, "condition": "sunny"}

    async def test_stream_with_message_detects_hitl_interrupt(self):
        """When state has interrupts, final Message has status=awaiting_hitl."""
        chunks = ["Waiting for approval"]

        ai_msg = MagicMock()
        ai_msg.content = ""
        ai_msg.tool_calls = [{"name": "delete_file", "args": {"path": "/tmp/x"}, "id": "tc-1"}]

        interrupt = MagicMock()
        graph = _make_streaming_graph(
            chunks,
            final_messages=[ai_msg],
            interrupts=(interrupt,),
        )

        runner = DeepAgentRunner(graph)
        collected = []
        async for item in runner.stream_with_message("thread-1", "delete file"):
            collected.append(item)

        final_message = collected[-1]
        assert isinstance(final_message, Message)
        assert final_message.status == MessageStatus.AWAITING_HITL

    async def test_stream_with_message_no_chunks_yields_message(self):
        """When stream produces 0 AI chunks but graph completes, still yield a Message."""
        # Empty chunks — the stream yields nothing, but get_state still works
        graph = _make_streaming_graph([])

        runner = DeepAgentRunner(graph)
        collected = []
        async for item in runner.stream_with_message("thread-1", "hello"):
            collected.append(item)

        # Should have exactly one item: the final Message
        assert len(collected) == 1
        assert isinstance(collected[0], Message)
        assert collected[0].role == MessageRole.AI

    async def test_stream_with_message_raises_on_error(self):
        """When astream raises, AgentError is raised."""
        mock_graph = AsyncMock()

        async def _astream_error(_input, _config=None, _stream_mode=None):
            raise RuntimeError("LLM streaming error")
            yield

        mock_graph.astream = _astream_error

        runner = DeepAgentRunner(mock_graph)
        with pytest.raises(AgentError, match="Streaming error"):
            collected = []
            async for item in runner.stream_with_message("thread-1", "hello"):
                collected.append(item)
