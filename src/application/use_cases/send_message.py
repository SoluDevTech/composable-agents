import logging
import time
from typing import Any

from src.domain.entities.message import Message, MessageRole
from src.domain.errors.hitl import InvalidHitlActionError
from src.domain.errors.messages import ErrorMessage
from src.domain.logging.messages import LogMessage
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.thread_repository import ThreadRepository

logger = logging.getLogger(__name__)


class SendMessageUseCase:
    """Envoie un message ou une decision HITL a l'agent et retourne la reponse."""

    def __init__(self, registry: AgentRegistry, threads: ThreadRepository) -> None:
        self._registry = registry
        self._threads = threads

    @staticmethod
    def _is_duplicate_human_message(messages: list[Message], message: str) -> bool:
        """Detect duplicate HUMAN message submissions (crash/retry scenario).

        When a request crashes before the AI response is persisted, the last DB message
        is HUMAN with status=None. On client retry, this check prevents storing a
        duplicate HUMAN message in the DB.

        NOTE: The graph invocation still proceeds (LangGraph will add the human message
        to its internal checkpoint state). This is intentional — the graph needs to be
        invoked to produce a response. The trade-off is that the LangGraph checkpoint
        may accumulate duplicate human messages, but the DB projection remains clean.
        """
        if not messages:
            return False
        last = messages[-1]
        return (
            last.role == MessageRole.HUMAN
            and last.content == message
            and last.status is None
        )

    async def execute(
        self,
        thread_id: str,
        *,
        message: str | None = None,
        action: str | None = None,
        tool_call_id: str | None = None,
        reason: str | None = None,
        edits: dict[str, Any] | None = None,
    ) -> Message:
        thread = await self._threads.get(thread_id)
        runner = await self._registry.get_runner(thread.agent_name)

        if message is not None:
            logger.info(LogMessage.CHAT_SENDING_HUMAN, thread_id, thread.agent_name)
            if not self._is_duplicate_human_message(thread.messages, message):
                human_msg = Message(role=MessageRole.HUMAN, content=message)
                await self._threads.add_message(thread_id, human_msg)
            else:
                logger.info(LogMessage.CHAT_SKIP_DUPLICATE_HUMAN, thread_id)
            start = time.monotonic()
            response = await runner.invoke(thread_id, message)
            elapsed = time.monotonic() - start
            logger.info(
                LogMessage.CHAT_INVOKE_COMPLETE,
                thread_id,
                thread.agent_name,
                elapsed,
                response.status,
                len(response.content or ""),
            )
        else:
            logger.info(
                LogMessage.CHAT_HITL_RECEIVED,
                thread_id,
                thread.agent_name,
                action,
                tool_call_id,
            )
            start = time.monotonic()
            match action:
                case "approve":
                    response = await runner.approve_hitl(thread_id, tool_call_id)
                case "reject":
                    response = await runner.reject_hitl(thread_id, tool_call_id, reason)
                case "edit":
                    response = await runner.edit_hitl(thread_id, tool_call_id, edits)
                case _:
                    raise InvalidHitlActionError(ErrorMessage.INVALID_HITL_ACTION.format(action=action))
            elapsed = time.monotonic() - start
            logger.info(
                LogMessage.CHAT_HITL_COMPLETE,
                thread_id,
                thread.agent_name,
                elapsed,
                response.status,
            )

        await self._threads.add_message(thread_id, response)
        return response
