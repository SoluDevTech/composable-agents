from typing import AsyncIterator
from src.domain.ports.agent_runner import AgentRunner
from src.domain.entities.message import Message, MessageRole


class FakeAgentRunner(AgentRunner):
    def __init__(self):
        self._responses: dict[str, str] = {}
        self._default_response = "I am a fake agent."

    def set_response(self, thread_id: str, response: str):
        self._responses[thread_id] = response

    async def invoke(self, thread_id: str, message: str) -> Message:
        content = self._responses.get(thread_id, self._default_response)
        return Message(role=MessageRole.AI, content=content)

    async def stream(self, thread_id: str, message: str) -> AsyncIterator[str]:
        content = self._responses.get(thread_id, self._default_response)
        for word in content.split():
            yield word + " "

    async def approve_hitl(self, thread_id: str, tool_call_id: str) -> Message:
        return Message(role=MessageRole.AI, content="Action approved.")

    async def reject_hitl(self, thread_id: str, tool_call_id: str, reason: str | None = None) -> Message:
        return Message(role=MessageRole.AI, content=f"Action rejected: {reason}")

    async def edit_hitl(self, thread_id: str, tool_call_id: str, edits: dict) -> Message:
        return Message(role=MessageRole.AI, content="Action edited and approved.")
