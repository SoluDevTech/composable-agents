"""Tests for DeepAgentRunner tracing integration.

Uses the shared ``mock_tracing_provider`` fixture (external.py) and
``noop_tracing`` fixture (conftest.py). The graph is mocked (external).
Tests exercise the public ``invoke`` and ``stream`` methods and verify
tracing callbacks are passed via the graph config.
"""

from unittest.mock import AsyncMock, MagicMock

from src.domain.entities.trace_event import TraceEventType
from src.infrastructure.deepagent.adapter import DeepAgentRunner


def _msg(content="Hello"):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


def _streaming_graph(tracing_provider=None):  # noqa: ARG001
    """Build a graph whose astream yields a single content chunk.

    Returns the graph and the astream MagicMock wrapper so tests can inspect
    the config passed to the underlying call.
    """
    graph = AsyncMock()
    graph.nodes = {}
    astream_mock = MagicMock()

    async def _astream(_input, **kwargs):
        astream_mock(_input, **kwargs)
        chunk = MagicMock()
        chunk.content = "chunk"
        chunk.type = "AIMessageChunk"
        chunk.additional_kwargs = {}
        chunk.tool_call_chunks = None
        yield (chunk, {"langgraph_checkpoint_ns": "Agent"})

    graph.astream = _astream
    final = _msg("chunk")
    state = MagicMock()
    state.values = {"messages": [final]}
    state.interrupts = ()
    graph.get_state = MagicMock(return_value=state)
    return graph, astream_mock


def _config_from_call(astream_mock):
    """Extract the config dict from the recorded astream call."""
    call = astream_mock.call_args
    return call[1]["config"] if "config" in call[1] else call[0][1]


class TestInvokeTracing:
    async def test_invoke_with_tracing_injects_callbacks(self, mock_tracing_provider):
        # Arrange
        mock_callback = MagicMock()
        mock_tracing_provider.get_callbacks.return_value = [mock_callback]
        graph, astream = _streaming_graph()

        # Act
        runner = DeepAgentRunner(graph, tracing_provider=mock_tracing_provider)
        await runner.invoke("thread-1", "Hi", "turn-1")

        # Assert
        config = _config_from_call(astream)
        assert "callbacks" in config
        assert mock_callback in config["callbacks"]

    async def test_invoke_without_tracing_has_no_callbacks(self):
        # Arrange
        graph, astream = _streaming_graph()

        # Act
        runner = DeepAgentRunner(graph)
        await runner.invoke("thread-1", "Hi", "turn-1")

        # Assert
        config = _config_from_call(astream)
        assert "callbacks" not in config

    async def test_invoke_with_noop_tracing_has_no_callbacks(self, noop_tracing):
        # Arrange
        graph, astream = _streaming_graph()

        # Act
        runner = DeepAgentRunner(graph, tracing_provider=noop_tracing)
        await runner.invoke("thread-1", "Hi", "turn-1")

        # Assert
        config = _config_from_call(astream)
        assert "callbacks" not in config


class TestStreamTracing:
    async def test_stream_with_tracing_returns_content_events(self, mock_tracing_provider):
        # Arrange
        mock_callback = MagicMock()
        mock_tracing_provider.get_callbacks.return_value = [mock_callback]
        graph, astream = _streaming_graph()

        # Act
        runner = DeepAgentRunner(graph, tracing_provider=mock_tracing_provider)
        events = [e async for e in runner.stream("thread-1", "Hi", "turn-1")]

        # Assert: HUMAN + CONTENT + AI_MESSAGE = 3
        assert len(events) == 3
        # Find the CONTENT event (between HUMAN and AI_MESSAGE).
        content_events = [e for e in events if e.type == TraceEventType.CONTENT]
        assert len(content_events) == 1
        assert content_events[0].content == "chunk"

        config = _config_from_call(astream)
        assert "callbacks" in config
        assert mock_callback in config["callbacks"]
