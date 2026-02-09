from src.application.requests.chat import ChatRequest
from src.domain.entities.message import Message, MessageRole
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.thread_repository import ThreadRepository


class SendMessageUseCase:
    """Envoie un message ou une decision HITL a l'agent et retourne la reponse."""

    def __init__(self, registry: AgentRegistry, threads: ThreadRepository):
        self._registry = registry
        self._threads = threads

    async def execute(self, thread_id: str, request: ChatRequest) -> Message:
        thread = await self._threads.get(thread_id)
        runner = await self._registry.get_runner(thread.agent_name)

        if request.message is not None:
            human_msg = Message(role=MessageRole.HUMAN, content=request.message)
            await self._threads.add_message(thread_id, human_msg)
            response = await runner.invoke(thread_id, request.message)
        else:
            match request.action:
                case "approve":
                    response = await runner.approve_hitl(thread_id, request.tool_call_id)
                case "reject":
                    response = await runner.reject_hitl(
                        thread_id, request.tool_call_id, request.reason
                    )
                case "edit":
                    response = await runner.edit_hitl(
                        thread_id, request.tool_call_id, request.edits
                    )

        await self._threads.add_message(thread_id, response)
        return response
