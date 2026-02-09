import pytest
from src.application.requests.chat import ChatRequest
from src.application.use_cases.send_message import SendMessageUseCase
from src.infrastructure.memory_thread.adapter import InMemoryThreadRepository
from tests.doubles.fake_agent_registry import FakeAgentRegistry


class TestSendMessageUseCase:
    @pytest.mark.asyncio
    async def test_sends_message_and_saves_response(self):
        registry = FakeAgentRegistry()
        runner = registry.register("test-agent")
        runner.set_response("placeholder", "Hello human!")

        threads = InMemoryThreadRepository()
        thread = await threads.create("test-agent")
        runner.set_response(thread.id, "Hello human!")

        use_case = SendMessageUseCase(registry, threads)
        response = await use_case.execute(thread.id, ChatRequest(message="Hello agent!"))

        assert response.content == "Hello human!"
        updated_thread = await threads.get(thread.id)
        assert len(updated_thread.messages) == 2  # human + ai

    @pytest.mark.asyncio
    async def test_approve_hitl_saves_response(self):
        registry = FakeAgentRegistry()
        registry.register("test-agent")
        threads = InMemoryThreadRepository()
        thread = await threads.create("test-agent")

        use_case = SendMessageUseCase(registry, threads)
        request = ChatRequest(tool_call_id="tc-1", action="approve")
        response = await use_case.execute(thread.id, request)

        assert "approved" in response.content.lower()
        updated_thread = await threads.get(thread.id)
        assert len(updated_thread.messages) == 1  # ai only (no human message for HITL)

    @pytest.mark.asyncio
    async def test_reject_hitl_saves_response(self):
        registry = FakeAgentRegistry()
        registry.register("test-agent")
        threads = InMemoryThreadRepository()
        thread = await threads.create("test-agent")

        use_case = SendMessageUseCase(registry, threads)
        request = ChatRequest(tool_call_id="tc-1", action="reject", reason="Too risky")
        response = await use_case.execute(thread.id, request)

        assert "rejected" in response.content.lower()
        updated_thread = await threads.get(thread.id)
        assert len(updated_thread.messages) == 1

    @pytest.mark.asyncio
    async def test_edit_hitl_saves_response(self):
        registry = FakeAgentRegistry()
        registry.register("test-agent")
        threads = InMemoryThreadRepository()
        thread = await threads.create("test-agent")

        use_case = SendMessageUseCase(registry, threads)
        request = ChatRequest(tool_call_id="tc-1", action="edit", edits={"param": "value"})
        response = await use_case.execute(thread.id, request)

        assert "edited" in response.content.lower()
        updated_thread = await threads.get(thread.id)
        assert len(updated_thread.messages) == 1
