import pytest
from unittest.mock import AsyncMock, MagicMock

from src.domain.entities.message import MessageRole
from src.infrastructure.deepagent.adapter import DeepAgentRunner
from tests.doubles.fake_tracing_provider import FakeTracingProvider


class TestDeepAgentRunnerTracing:
    @pytest.mark.asyncio
    async def test_invoke_with_tracing_injects_callbacks(self):
        mock_callback = MagicMock()
        tracing = FakeTracingProvider(callbacks=[mock_callback])

        mock_graph = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.content = "Hello"
        mock_msg.tool_calls = None
        mock_graph.ainvoke.return_value = {"messages": [mock_msg]}
        mock_graph.get_state = MagicMock(return_value=MagicMock(interrupts=()))

        runner = DeepAgentRunner(mock_graph, tracing_provider=tracing)
        result = await runner.invoke("thread-1", "Hi")

        assert result.role == MessageRole.AI
        assert result.content == "Hello"

        call_kwargs = mock_graph.ainvoke.call_args
        config = call_kwargs[1]["config"] if "config" in call_kwargs[1] else call_kwargs[0][1]
        assert "callbacks" in config
        assert mock_callback in config["callbacks"]

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_invoke_with_noop_tracing_no_callbacks(self):
        """When tracing provider returns empty callbacks, no callbacks key in config."""
        tracing = FakeTracingProvider(callbacks=[])

        mock_graph = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.content = "Hello"
        mock_msg.tool_calls = None
        mock_graph.ainvoke.return_value = {"messages": [mock_msg]}
        mock_graph.get_state = MagicMock(return_value=MagicMock(interrupts=()))

        runner = DeepAgentRunner(mock_graph, tracing_provider=tracing)
        await runner.invoke("thread-1", "Hi")

        call_kwargs = mock_graph.ainvoke.call_args
        config = call_kwargs[1]["config"] if "config" in call_kwargs[1] else call_kwargs[0][1]
        assert "callbacks" not in config

    @pytest.mark.asyncio
    async def test_stream_with_tracing_injects_callbacks(self):
        mock_callback = MagicMock()
        tracing = FakeTracingProvider(callbacks=[mock_callback])

        mock_graph = AsyncMock()

        async def mock_astream(*args, **kwargs):
            mock_msg = MagicMock()
            mock_msg.content = "chunk"
            yield ("ai", mock_msg)

        mock_graph.astream = mock_astream

        runner = DeepAgentRunner(mock_graph, tracing_provider=tracing)

        chunks = []
        async for chunk in runner.stream("thread-1", "Hi"):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0] == "chunk"

    @pytest.mark.asyncio
    async def test_build_config_with_tracing(self):
        mock_callback = MagicMock()
        tracing = FakeTracingProvider(callbacks=[mock_callback])

        runner = DeepAgentRunner(MagicMock(), tracing_provider=tracing)
        config = runner._build_config("thread-1")

        assert config["configurable"]["thread_id"] == "thread-1"
        assert config["callbacks"] == [mock_callback]

    @pytest.mark.asyncio
    async def test_build_config_without_tracing(self):
        runner = DeepAgentRunner(MagicMock())
        config = runner._build_config("thread-1")

        assert config["configurable"]["thread_id"] == "thread-1"
        assert "callbacks" not in config
