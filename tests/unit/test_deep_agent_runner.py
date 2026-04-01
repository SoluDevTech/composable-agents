"""Tests for DeepAgentRunner.

Graph is mocked (external LLM boundary via LangGraph).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.entities.message import MessageRole, MessageStatus
from src.domain.exceptions import AgentError
from src.infrastructure.deepagent.adapter import DeepAgentRunner


def _make_graph(messages, interrupts=(), state_values=None):
    """Create a mock graph with ainvoke result and get_state."""
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {"messages": messages}
    state = MagicMock()
    state.interrupts = interrupts
    state.values = state_values or {}
    mock_graph.get_state = MagicMock(return_value=state)
    return mock_graph


class TestDeepAgentRunner:
    async def test_invoke_returns_message(self):
        mock_msg = MagicMock()
        mock_msg.content = "Hello from agent"
        mock_msg.tool_calls = None
        graph = _make_graph([mock_msg])

        runner = DeepAgentRunner(graph)
        result = await runner.invoke("thread-1", "Hello")

        assert result.role == MessageRole.AI
        assert result.content == "Hello from agent"
        assert result.status == MessageStatus.COMPLETED
        graph.ainvoke.assert_called_once()

    async def test_invoke_uses_only_last_message_tool_calls(self):
        """Only tool_calls from the last message are returned, not intermediate ones."""
        human_msg = MagicMock(spec=[])
        human_msg.type = "human"
        ai_with_tools = MagicMock()
        ai_with_tools.tool_calls = [{"name": "word_count", "args": {"text": "hello"}, "id": "tc-1"}]
        tool_msg = MagicMock(spec=[])
        final_ai = MagicMock()
        final_ai.content = "The text has 1 word."
        final_ai.tool_calls = []
        graph = _make_graph([human_msg, ai_with_tools, tool_msg, final_ai])

        runner = DeepAgentRunner(graph)
        result = await runner.invoke("thread-1", "count words in hello")

        assert result.content == "The text has 1 word."
        assert result.tool_calls is None
        assert result.status == MessageStatus.COMPLETED

    async def test_invoke_detects_hitl_interruption(self):
        """When get_state() reports interrupts, status is awaiting_hitl."""
        ai_msg = MagicMock()
        ai_msg.content = ""
        ai_msg.tool_calls = [{"name": "word_count", "args": {"text": "hi"}, "id": "tc-1"}]
        interrupt = MagicMock()
        graph = _make_graph([ai_msg], interrupts=(interrupt,))

        runner = DeepAgentRunner(graph)
        result = await runner.invoke("thread-1", "count words")

        assert result.status == MessageStatus.AWAITING_HITL
        assert result.tool_calls is not None
        assert result.content == ""

    async def test_invoke_completed_when_no_interrupts(self):
        """When get_state() reports no interrupts, status is completed."""
        mock_msg = MagicMock()
        mock_msg.content = "Done"
        mock_msg.tool_calls = None
        graph = _make_graph([mock_msg], interrupts=())

        runner = DeepAgentRunner(graph)
        result = await runner.invoke("thread-1", "Hello")

        assert result.status == MessageStatus.COMPLETED

    async def test_invoke_returns_none_tool_calls_when_last_message_has_none(self):
        """When the final AI message has no tool_calls, result.tool_calls is None."""
        old_human = MagicMock(spec=[])
        old_human.type = "human"
        old_ai = MagicMock()
        old_ai.tool_calls = [{"name": "old_tool", "args": {}, "id": "tc-old"}]

        new_human = MagicMock(spec=[])
        new_human.type = "human"
        final_ai = MagicMock()
        final_ai.content = "New response"
        final_ai.tool_calls = []

        graph = _make_graph([old_human, old_ai, new_human, final_ai])

        runner = DeepAgentRunner(graph)
        result = await runner.invoke("thread-1", "new question")

        assert result.content == "New response"
        assert result.tool_calls is None

    async def test_invoke_raises_on_error(self):
        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = RuntimeError("LLM error")

        runner = DeepAgentRunner(mock_graph)
        with pytest.raises(AgentError, match="Agent execution error"):
            await runner.invoke("thread-1", "Hello")

    # --- HITL _build_response integration tests ---

    async def test_approve_hitl_detects_subsequent_interrupt(self):
        """After approve, if graph returns new interrupts, status is AWAITING_HITL."""
        human_msg = MagicMock(spec=[])
        human_msg.type = "human"
        ai_with_tools = MagicMock()
        ai_with_tools.tool_calls = [{"name": "search", "args": {"q": "test"}, "id": "tc-2"}]
        tool_result = MagicMock(spec=[])
        final_ai = MagicMock()
        final_ai.content = ""
        final_ai.tool_calls = [{"name": "deploy", "args": {}, "id": "tc-3"}]

        interrupt = MagicMock()
        graph = _make_graph(
            [human_msg, ai_with_tools, tool_result, final_ai],
            interrupts=(interrupt,),
        )

        runner = DeepAgentRunner(graph)
        result = await runner.approve_hitl("thread-1", "tc-1")

        assert result.status == MessageStatus.AWAITING_HITL
        assert result.tool_calls is not None
        assert any(tc["name"] == "deploy" for tc in result.tool_calls)

    async def test_reject_hitl_detects_subsequent_interrupt(self):
        """After reject, if graph returns new interrupts, status is AWAITING_HITL."""
        human_msg = MagicMock(spec=[])
        human_msg.type = "human"
        ai_with_tools = MagicMock()
        ai_with_tools.tool_calls = [{"name": "delete_file", "args": {"path": "/tmp"}, "id": "tc-5"}]
        tool_result = MagicMock(spec=[])
        final_ai = MagicMock()
        final_ai.content = ""
        final_ai.tool_calls = [{"name": "confirm_delete", "args": {}, "id": "tc-6"}]

        interrupt = MagicMock()
        graph = _make_graph(
            [human_msg, ai_with_tools, tool_result, final_ai],
            interrupts=(interrupt,),
        )

        runner = DeepAgentRunner(graph)
        result = await runner.reject_hitl("thread-1", "tc-4", reason="not safe")

        assert result.status == MessageStatus.AWAITING_HITL
        assert result.tool_calls is not None
        assert any(tc["name"] == "confirm_delete" for tc in result.tool_calls)

    async def test_edit_hitl_detects_subsequent_interrupt(self):
        """After edit, if graph returns new interrupts, status is AWAITING_HITL."""
        human_msg = MagicMock(spec=[])
        human_msg.type = "human"
        ai_with_tools = MagicMock()
        ai_with_tools.tool_calls = [{"name": "send_email", "args": {"to": "a@b.com"}, "id": "tc-8"}]
        tool_result = MagicMock(spec=[])
        final_ai = MagicMock()
        final_ai.content = ""
        final_ai.tool_calls = [{"name": "confirm_send", "args": {}, "id": "tc-9"}]

        interrupt = MagicMock()
        # State needs messages with matching tool_call_id for tool name resolution
        state_msg = MagicMock()
        state_msg.tool_calls = [{"name": "send_email", "args": {"to": "a@b.com"}, "id": "tc-7"}]
        graph = _make_graph(
            [human_msg, ai_with_tools, tool_result, final_ai],
            interrupts=(interrupt,),
            state_values={"messages": [state_msg]},
        )

        runner = DeepAgentRunner(graph)
        result = await runner.edit_hitl("thread-1", "tc-7", edits={"to": "x@y.com"})

        assert result.status == MessageStatus.AWAITING_HITL
        assert result.tool_calls is not None
        assert any(tc["name"] == "confirm_send" for tc in result.tool_calls)
        # Verify ainvoke was called with edited action containing resolved tool name
        call_args = graph.ainvoke.call_args
        command = call_args[0][0]
        decision = command.resume["decisions"][0]
        assert decision["type"] == "edit"
        assert decision["edited_action"]["name"] == "send_email"
        assert decision["edited_action"]["args"] == {"to": "x@y.com"}

    async def test_approve_hitl_completed_when_no_interrupts(self):
        """After approve with no further interrupts, status is COMPLETED with no tool_calls."""
        human_msg = MagicMock(spec=[])
        human_msg.type = "human"
        ai_with_tools = MagicMock()
        ai_with_tools.tool_calls = [{"name": "search", "args": {"q": "test"}, "id": "tc-10"}]
        tool_result = MagicMock(spec=[])
        final_ai = MagicMock()
        final_ai.content = "Search complete. Found 3 results."
        final_ai.tool_calls = []

        graph = _make_graph(
            [human_msg, ai_with_tools, tool_result, final_ai],
            interrupts=(),
        )

        runner = DeepAgentRunner(graph)
        result = await runner.approve_hitl("thread-1", "tc-1")

        assert result.status == MessageStatus.COMPLETED
        assert result.content == "Search complete. Found 3 results."
        assert result.tool_calls is None

    async def test_reject_hitl_excludes_rejected_tool_calls(self):
        """After reject, the rejected tool_calls are not in the response."""
        human_msg = MagicMock(spec=[])
        human_msg.type = "human"
        ai_with_tools = MagicMock()
        ai_with_tools.tool_calls = [{"name": "word_count", "args": {"text": "test"}, "id": "tc-1"}]
        final_ai = MagicMock()
        final_ai.content = "I can count manually: 1 word."
        final_ai.tool_calls = []

        graph = _make_graph(
            [human_msg, ai_with_tools, final_ai],
            interrupts=(),
        )

        runner = DeepAgentRunner(graph)
        result = await runner.reject_hitl("thread-1", "tc-1", reason="not allowed")

        assert result.status == MessageStatus.COMPLETED
        assert result.content == "I can count manually: 1 word."
        assert result.tool_calls is None

    # --- Structured output tests ---

    async def test_build_response_extracts_structured_response_dict(self):
        """When result contains structured_response dict, it appears in Message."""
        mock_msg = MagicMock()
        mock_msg.content = "Weather report"
        mock_msg.tool_calls = None
        graph = _make_graph([mock_msg])
        graph.ainvoke.return_value = {
            "messages": [mock_msg],
            "structured_response": {"temperature": 22, "condition": "sunny"},
        }

        runner = DeepAgentRunner(graph)
        result = await runner.invoke("thread-1", "weather?")

        assert result.structured_response == {"temperature": 22, "condition": "sunny"}

    async def test_build_response_extracts_structured_response_model_dump(self):
        """When structured_response is a Pydantic model, it's converted via model_dump()."""
        mock_msg = MagicMock()
        mock_msg.content = "Report"
        mock_msg.tool_calls = None

        pydantic_obj = MagicMock()
        pydantic_obj.model_dump.return_value = {"temperature": 15, "condition": "cloudy"}

        graph = _make_graph([mock_msg])
        graph.ainvoke.return_value = {
            "messages": [mock_msg],
            "structured_response": pydantic_obj,
        }

        runner = DeepAgentRunner(graph)
        result = await runner.invoke("thread-1", "weather?")

        assert result.structured_response == {"temperature": 15, "condition": "cloudy"}
        pydantic_obj.model_dump.assert_called_once()

    async def test_build_response_no_structured_response(self):
        """When result has no structured_response, field is None."""
        mock_msg = MagicMock()
        mock_msg.content = "Hello"
        mock_msg.tool_calls = None
        graph = _make_graph([mock_msg])

        runner = DeepAgentRunner(graph)
        result = await runner.invoke("thread-1", "hi")

        assert result.structured_response is None
