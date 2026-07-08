"""Tests for SendMessageUseCase.

Uses real PostgresThreadRepository (internal, from conftest).
Uses mock_agent_runner (external LLM boundary, from external.py).
A small real fake registry wraps the mock runner.
"""

import pytest

from src.application.use_cases.send_message import SendMessageUseCase
from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.errors.hitl import InvalidHitlActionError
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.agent_runner import AgentRunner


class _FakeRegistry(AgentRegistry):
    """Real in-test registry that returns a single runner."""

    def __init__(self, runner: AgentRunner) -> None:
        self._runner = runner

    async def get_runner(self, agent_name: str) -> AgentRunner:  # noqa: ARG002
        return self._runner

    async def list_agents(self) -> list[str]:
        return ["test-agent"]

    async def invalidate(self, agent_name: str) -> None:
        pass

    async def close(self) -> None:
        pass


class TestSendMessageUseCase:
    @pytest.fixture
    def registry(self, mock_agent_runner):
        return _FakeRegistry(mock_agent_runner)

    @pytest.fixture
    def use_case(self, registry, thread_repo):
        return SendMessageUseCase(registry, thread_repo)

    async def test_sends_message_and_saves_response(self, use_case, mock_agent_runner, thread_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        mock_agent_runner.invoke.return_value = Message(
            role=MessageRole.AI, content="Hello human!", status=MessageStatus.COMPLETED
        )

        # Act
        response = await use_case.execute(thread.id, message="Hello agent!")

        # Assert
        assert response.content == "Hello human!"
        updated = await thread_repo.get(thread.id)
        assert len(updated.messages) == 2

    async def test_approve_hitl_saves_response(self, use_case, mock_agent_runner, thread_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        mock_agent_runner.approve_hitl.return_value = Message(role=MessageRole.AI, content="Action approved.")

        # Act
        response = await use_case.execute(thread.id, action="approve", tool_call_id="tc-1")

        # Assert
        assert "approved" in response.content.lower()
        updated = await thread_repo.get(thread.id)
        assert len(updated.messages) == 1

    async def test_reject_hitl_saves_response(self, use_case, mock_agent_runner, thread_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        mock_agent_runner.reject_hitl.return_value = Message(
            role=MessageRole.AI, content="Action rejected: Too risky"
        )

        # Act
        response = await use_case.execute(thread.id, action="reject", tool_call_id="tc-1", reason="Too risky")

        # Assert
        assert "rejected" in response.content.lower()
        updated = await thread_repo.get(thread.id)
        assert len(updated.messages) == 1

    async def test_edit_hitl_saves_response(self, use_case, mock_agent_runner, thread_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        mock_agent_runner.edit_hitl.return_value = Message(
            role=MessageRole.AI, content="Action edited and approved."
        )

        # Act
        response = await use_case.execute(thread.id, action="edit", tool_call_id="tc-1", edits={"param": "value"})

        # Assert
        assert "edited" in response.content.lower()
        updated = await thread_repo.get(thread.id)
        assert len(updated.messages) == 1

    async def test_unsupported_hitl_action_raises(self, use_case, thread_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")

        # Act / Assert
        with pytest.raises(InvalidHitlActionError, match="Unsupported HITL action"):
            await use_case.execute(thread.id, action="unknown_action", tool_call_id="tc-1")

    async def test_execute_skips_duplicate_human_message(self, use_case, mock_agent_runner, thread_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        await thread_repo.add_message(thread.id, Message(role=MessageRole.HUMAN, content="Hello agent!"))
        mock_agent_runner.invoke.return_value = Message(role=MessageRole.AI, content="Hi!")

        # Act
        await use_case.execute(thread.id, message="Hello agent!")

        # Assert
        updated = await thread_repo.get(thread.id)
        human_msgs = [m for m in updated.messages if m.role == MessageRole.HUMAN]
        assert len(human_msgs) == 1
