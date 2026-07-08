"""Tests for DeepAgentRunner tracing integration.

Uses the shared ``mock_tracing_provider`` fixture (external.py) and
``noop_tracing`` fixture (conftest.py). The graph is mocked (external).
Tests exercise the public ``invoke`` and ``stream`` methods and verify
tracing callbacks are passed via the graph config.
"""

from unittest.mock import AsyncMock, MagicMock

from src.domain.entities.stream_event import StreamEventType
from src.infrastructure.deepagent.adapter import DeepAgentRunner


def _config_from_call(mock_ainvoke):
    """Extract the config dict from a mock ainvoke call."""
    call = mock_ainvoke.call_args
    return call[1]["config"] if "config" in call[1] else call[0][1]


class TestInvokeTracing:
    async def test_invoke_with_tracing_injects_callbacks(self, mock_tracing_provider):
        # Arrange
        mock_callback = MagicMock()
        mock_tracing_provider.get_callbacks.return_value = [mock_callback]
        graph = AsyncMock()
        graph.nodes = {}
        msg = MagicMock()
        msg.content = "Hello"
        msg.tool_calls = None
        graph.ainvoke.return_value = {"messages": [msg]}
        graph.get_state = MagicMock(return_value=MagicMock(interrupts=()))

        # Act
        runner = DeepAgentRunner(graph, tracing_provider=mock_tracing_provider)
        await runner.invoke("thread-1", "Hi")

        # Assert
        config = _config_from_call(graph.ainvoke)
        assert "callbacks" in config
        assert mock_callback in config["callbacks"]

    async def test_invoke_without_tracing_has_no_callbacks(self):
        # Arrange
        graph = AsyncMock()
        graph.nodes = {}
        msg = MagicMock()
        msg.content = "Hello"
        msg.tool_calls = None
        graph.ainvoke.return_value = {"messages": [msg]}
        graph.get_state = MagicMock(return_value=MagicMock(interrupts=()))

        # Act
        runner = DeepAgentRunner(graph)
        await runner.invoke("thread-1", "Hi")

        # Assert
        config = _config_from_call(graph.ainvoke)
        assert "callbacks" not in config

    async def test_invoke_with_noop_tracing_has_no_callbacks(self, noop_tracing):
        # Arrange
        graph = AsyncMock()
        graph.nodes = {}
        msg = MagicMock()
        msg.content = "Hello"
        msg.tool_calls = None
        graph.ainvoke.return_value = {"messages": [msg]}
        graph.get_state = MagicMock(return_value=MagicMock(interrupts=()))

        # Act
        runner = DeepAgentRunner(graph, tracing_provider=noop_tracing)
        await runner.invoke("thread-1", "Hi")

        # Assert
        config = _config_from_call(graph.ainvoke)
        assert "callbacks" not in config


class TestStreamTracing:
    async def test_stream_with_tracing_returns_content_events(self, mock_tracing_provider):
        # Arrange
        mock_callback = MagicMock()
        mock_tracing_provider.get_callbacks.return_value = [mock_callback]
        graph = AsyncMock()
        graph.nodes = {}

        async def mock_astream(*_args, **_kwargs):
            chunk = MagicMock()
            chunk.content = "chunk"
            chunk.type = "AIMessageChunk"
            chunk.additional_kwargs = {}
            yield (chunk, {"langgraph_node": "agent"})

        graph.astream = mock_astream
        graph.get_state = MagicMock(
            return_value=MagicMock(
                values={"messages": [MagicMock(content="chunk", tool_calls=None)]},
                interrupts=(),
            )
        )

        # Act
        runner = DeepAgentRunner(graph, tracing_provider=mock_tracing_provider)
        events = [e async for e in runner.stream("thread-1", "Hi")]

        # Assert
        assert len(events) == 1
        assert events[0].type == StreamEventType.CONTENT
        assert events[0].data == "chunk"
