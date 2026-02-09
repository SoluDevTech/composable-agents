from collections.abc import AsyncGenerator
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.thread_repository import ThreadRepository
from src.domain.entities.message import Message, MessageRole


class StreamMessageUseCase:
    """Envoie un message a l'agent et streame la reponse."""

    def __init__(self, registry: AgentRegistry, threads: ThreadRepository):
        self._registry = registry
        self._threads = threads

    async def execute(self, thread_id: str, message: str) -> AsyncGenerator[str, None]:
        thread = await self._threads.get(thread_id)
        human_msg = Message(role=MessageRole.HUMAN, content=message)
        await self._threads.add_message(thread_id, human_msg)
        runner = await self._registry.get_runner(thread.agent_name)
        full_response = []
        async for chunk in runner.stream(thread_id, message):
            full_response.append(chunk)
            yield chunk
        ai_msg = Message(role=MessageRole.AI, content="".join(full_response))
        await self._threads.add_message(thread_id, ai_msg)
