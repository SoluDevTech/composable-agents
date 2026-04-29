"""Tests for DeepAgentRunner tracing integration.

Uses real NoopTracingProvider (internal) and MagicMock-based tracing provider
for non-empty callbacks. Graph is mocked (external LLM boundary).
"""

from unittest.mock import AsyncMock, MagicMock

from src.domain.entities.message import MessageRole
from src.domain.entities.stream_event import StreamEvent, StreamEventType
from src.infrastructure.deepagent.adapter import DeepAgentRunner


class TestDeepAgentRunnerTracing:
    async def test_invoke_with_tracing_injects_callbacks(self, mock_tracing_provider):
        mock_callback = MagicMock()
        mock_tracing_provider.get_callbacks.return_value = [mock_callback]

        mock_graph = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.content = "Hello"
        mock_msg.tool_calls = None
        mock_graph.ainvoke.return_value = {"messages": [mock_msg]}
        mock_graph.get_state = MagicMock(return_value=MagicMock(interrupts=()))

        runner = DeepAgentRunner(mock_graph, tracing_provider=mock_tracing_provider)
        result = await runner.invoke("thread-1", "Hi")

        assert result.role == MessageRole.AI
        assert result.content == "Hello"

        call_kwargs = mock_graph.ainvoke.call_args
        config = call_kwargs[1]["config"] if "config" in call_kwargs[1] else call_kwargs[0][1]
        assert "callbacks" in config
        assert mock_callback in config["callbacks"]

    async def test_invoke_without_tracing_no_callbacks(self):
        mock_graph = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.content = "Hello"
        mock_msg.tool_calls = None
        mock_graph.ainvoke.return_value = {"messages": [mock_msg]}
        mock_graph.get_state = MagicMock(return_value=MagicMock(interrupts=()))

        runner = DeepAgentRunner(mock_graph)
        await runner.invoke("thread-1", "Hi")

        call_kwargs = mock_graph.ainvoke.call_args
        config = call_kwargs[1]["config"] if "config" in call_kwargs[1] else call_kwargs[0][1]
        assert "callbacks" not in config

    async def test_invoke_with_noop_tracing_no_callbacks(self, noop_tracing):
        """When real NoopTracingProvider returns empty callbacks, no callbacks key in config."""
        mock_graph = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.content = "Hello"
        mock_msg.tool_calls = None
        mock_graph.ainvoke.return_value = {"messages": [mock_msg]}
        mock_graph.get_state = MagicMock(return_value=MagicMock(interrupts=()))

        runner = DeepAgentRunner(mock_graph, tracing_provider=noop_tracing)
        await runner.invoke("thread-1", "Hi")

        call_kwargs = mock_graph.ainvoke.call_args
        config = call_kwargs[1]["config"] if "config" in call_kwargs[1] else call_kwargs[0][1]
        assert "callbacks" not in config

    async def test_stream_with_tracing_injects_callbacks(self, mock_tracing_provider):
        mock_callback = MagicMock()
        mock_tracing_provider.get_callbacks.return_value = [mock_callback]

        mock_graph = AsyncMock()

        async def mock_astream(*_args, **_kwargs):
            mock_msg = MagicMock()
            mock_msg.content = "chunk"
            mock_msg.type = "AIMessageChunk"
            yield (mock_msg, {"langgraph_node": "agent"})

        mock_graph.astream = mock_astream
        mock_graph.get_state = MagicMock(
            return_value=MagicMock(values={"messages": [MagicMock(content="chunk", tool_calls=None)]}, interrupts=())
        )

        runner = DeepAgentRunner(mock_graph, tracing_provider=mock_tracing_provider)

        events = []
        async for event in runner.stream("thread-1", "Hi"):
            events.append(event)

        assert len(events) == 1
        assert events[0].type == StreamEventType.CONTENT
        assert events[0].data == "chunk"

    def test_build_config_with_tracing(self, mock_tracing_provider):
        mock_callback = MagicMock()
        mock_tracing_provider.get_callbacks.return_value = [mock_callback]

        runner = DeepAgentRunner(MagicMock(), tracing_provider=mock_tracing_provider)
        config = runner._build_config("thread-1")

        assert config["configurable"]["thread_id"] == "thread-1"
        assert config["callbacks"] == [mock_callback]

    def test_build_config_without_tracing(self):
        runner = DeepAgentRunner(MagicMock())
        config = runner._build_config("thread-1")

        assert config["configurable"]["thread_id"] == "thread-1"
        assert "callbacks" not in config
