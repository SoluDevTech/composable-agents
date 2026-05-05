"""Tests for DeepAgentRunner.stream_with_message().

Graph is mocked (external LLM boundary via LangGraph).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.entities.stream_event import StreamEventType
from src.domain.exceptions import AgentError
from src.infrastructure.deepagent.adapter import DeepAgentRunner


def _make_streaming_graph(
    chunks: list[tuple[StreamEventType, str]],
    final_messages: list | None = None,
    interrupts=(),
    state_values: dict | None = None,
    structured_response=None,
):
    mock_graph = AsyncMock()

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
    async def test_stream_with_message_yields_content_then_message(self):
        chunks = [(StreamEventType.CONTENT, "Hello "), (StreamEventType.CONTENT, "world!")]
        graph = _make_streaming_graph(chunks)
        runner = DeepAgentRunner(graph)
        collected = []
        async for event in runner.stream_with_message("thread-1", "hi"):
            collected.append(event)

        content_events = collected[:-1]
        final_event = collected[-1]

        assert all(e.type == StreamEventType.CONTENT for e in content_events)
        assert [e.data for e in content_events] == ["Hello ", "world!"]

        assert final_event.type == StreamEventType.MESSAGE
        msg = Message.model_validate_json(final_event.data)
        assert msg.role == MessageRole.AI
        assert msg.content == "Hello world!"
        assert msg.status == MessageStatus.COMPLETED

    async def test_stream_with_message_yields_thinking_then_content(self):
        chunks = [
            (StreamEventType.THINKING, "Let me think..."),
            (StreamEventType.CONTENT, "Here is the answer."),
        ]
        graph = _make_streaming_graph(chunks)
        runner = DeepAgentRunner(graph)
        collected = []
        async for event in runner.stream_with_message("thread-1", "hi"):
            collected.append(event)

        events = collected[:-1]
        assert events[0].type == StreamEventType.THINKING
        assert events[0].data == "Let me think..."
        assert events[1].type == StreamEventType.CONTENT
        assert events[1].data == "Here is the answer."

        final_event = collected[-1]
        msg = Message.model_validate_json(final_event.data)
        assert msg.thinking == "Let me think..."
        assert msg.content == "Here is the answer."

    async def test_stream_with_message_final_message_has_tool_calls(self):
        chunks = [(StreamEventType.CONTENT, "Processing...")]
        ai_msg = MagicMock()
        ai_msg.content = "Processing..."
        ai_msg.tool_calls = [{"name": "search", "args": {"q": "test"}, "id": "tc-1"}]
        graph = _make_streaming_graph(chunks, final_messages=[ai_msg])

        runner = DeepAgentRunner(graph)
        collected = []
        async for event in runner.stream_with_message("thread-1", "search for test"):
            collected.append(event)

        final_event = collected[-1]
        msg = Message.model_validate_json(final_event.data)
        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0]["name"] == "search"

    async def test_stream_with_message_final_message_has_structured_response(self):
        chunks = [(StreamEventType.CONTENT, "Weather report")]
        ai_msg = MagicMock()
        ai_msg.content = "Weather report"
        ai_msg.tool_calls = None
        graph = _make_streaming_graph(
            chunks, final_messages=[ai_msg],
            structured_response={"temperature": 22, "condition": "sunny"},
        )

        runner = DeepAgentRunner(graph)
        collected = []
        async for event in runner.stream_with_message("thread-1", "weather?"):
            collected.append(event)

        final_event = collected[-1]
        msg = Message.model_validate_json(final_event.data)
        assert msg.structured_response == {"temperature": 22, "condition": "sunny"}

    async def test_stream_with_message_detects_hitl_interrupt(self):
        chunks = [(StreamEventType.CONTENT, "Waiting for approval")]
        ai_msg = MagicMock()
        ai_msg.content = ""
        ai_msg.tool_calls = [{"name": "delete_file", "args": {"path": "/tmp/x"}, "id": "tc-1"}]
        interrupt = MagicMock()
        graph = _make_streaming_graph(chunks, final_messages=[ai_msg], interrupts=(interrupt,))

        runner = DeepAgentRunner(graph)
        collected = []
        async for event in runner.stream_with_message("thread-1", "delete file"):
            collected.append(event)

        final_event = collected[-1]
        msg = Message.model_validate_json(final_event.data)
        assert msg.status == MessageStatus.AWAITING_HITL

    async def test_stream_with_message_no_chunks_yields_message(self):
        graph = _make_streaming_graph([])
        runner = DeepAgentRunner(graph)
        collected = []
        async for event in runner.stream_with_message("thread-1", "hello"):
            collected.append(event)

        assert len(collected) == 1
        assert collected[0].type == StreamEventType.MESSAGE
        msg = Message.model_validate_json(collected[0].data)
        assert msg.role == MessageRole.AI

    async def test_stream_with_message_raises_on_error(self):
        mock_graph = AsyncMock()

        async def _astream_error(_input, _config=None, _stream_mode=None):
            raise RuntimeError("LLM streaming error")
            yield

        mock_graph.astream = _astream_error
        runner = DeepAgentRunner(mock_graph)
        with pytest.raises(AgentError, match="Streaming error"):
            collected = []
            async for event in runner.stream_with_message("thread-1", "hello"):
                collected.append(event)
