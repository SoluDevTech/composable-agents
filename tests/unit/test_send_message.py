"""Tests for SendMessageUseCase.

Uses real InMemoryThreadRepository (internal).
Uses AsyncMock for AgentRunner (external - calls LLM).
The DeepAgentRegistry is real but with patched factory to avoid LLM calls.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.requests.chat import ChatRequest
from src.application.use_cases.send_message import SendMessageUseCase
from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.ports.agent_runner import AgentRunner


class TestSendMessageUseCase:
    @pytest.fixture
    def runner(self):
        """AsyncMock spec'd to AgentRunner, simulating the external LLM adapter."""
        mock = AsyncMock(spec=AgentRunner)
        mock.invoke.return_value = Message(role=MessageRole.AI, content="Hello human!", status=MessageStatus.COMPLETED)
        mock.approve_hitl.return_value = Message(role=MessageRole.AI, content="Action approved.")
        mock.reject_hitl.return_value = Message(role=MessageRole.AI, content="Action rejected: Too risky")
        mock.edit_hitl.return_value = Message(role=MessageRole.AI, content="Action edited and approved.")
        return mock

    @pytest.fixture
    def registry(self, runner):
        """AsyncMock for AgentRegistry that returns our mocked runner."""
        mock = AsyncMock()
        mock.get_runner.return_value = runner
        mock.list_agents.return_value = ["test-agent"]
        return mock

    async def test_sends_message_and_saves_response(self, registry, runner, thread_repo):
        thread = await thread_repo.create("test-agent")
        use_case = SendMessageUseCase(registry, thread_repo)

        response = await use_case.execute(thread.id, ChatRequest(message="Hello agent!"))

        assert response.content == "Hello human!"
        runner.invoke.assert_awaited_once_with(thread.id, "Hello agent!")
        updated_thread = await thread_repo.get(thread.id)
        assert len(updated_thread.messages) == 2  # human + ai

    async def test_approve_hitl_saves_response(self, registry, runner, thread_repo):
        thread = await thread_repo.create("test-agent")
        use_case = SendMessageUseCase(registry, thread_repo)

        request = ChatRequest(tool_call_id="tc-1", action="approve")
        response = await use_case.execute(thread.id, request)

        assert "approved" in response.content.lower()
        runner.approve_hitl.assert_awaited_once_with(thread.id, "tc-1")
        updated_thread = await thread_repo.get(thread.id)
        assert len(updated_thread.messages) == 1  # ai only (no human message for HITL)

    async def test_reject_hitl_saves_response(self, registry, runner, thread_repo):
        thread = await thread_repo.create("test-agent")
        use_case = SendMessageUseCase(registry, thread_repo)

        request = ChatRequest(tool_call_id="tc-1", action="reject", reason="Too risky")
        response = await use_case.execute(thread.id, request)

        assert "rejected" in response.content.lower()
        runner.reject_hitl.assert_awaited_once_with(thread.id, "tc-1", "Too risky")
        updated_thread = await thread_repo.get(thread.id)
        assert len(updated_thread.messages) == 1

    async def test_edit_hitl_saves_response(self, registry, runner, thread_repo):
        thread = await thread_repo.create("test-agent")
        use_case = SendMessageUseCase(registry, thread_repo)

        request = ChatRequest(tool_call_id="tc-1", action="edit", edits={"param": "value"})
        response = await use_case.execute(thread.id, request)

        assert "edited" in response.content.lower()
        runner.edit_hitl.assert_awaited_once_with(thread.id, "tc-1", {"param": "value"})
        updated_thread = await thread_repo.get(thread.id)
        assert len(updated_thread.messages) == 1

    async def test_unsupported_hitl_action_raises_value_error(self, registry, thread_repo):
        """A HITL request with an unrecognized action should raise ValueError."""
        thread = await thread_repo.create("test-agent")
        use_case = SendMessageUseCase(registry, thread_repo)

        # Bypass Pydantic validation to simulate an unexpected action value
        request = MagicMock(spec=ChatRequest)
        request.message = None
        request.action = "unknown_action"
        request.tool_call_id = "tc-1"
        request.reason = None
        request.edits = None

        with pytest.raises(ValueError, match="Unsupported HITL action"):
            await use_case.execute(thread.id, request)
