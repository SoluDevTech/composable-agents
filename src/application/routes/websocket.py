import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from src.application.use_cases.stream_message import StreamMessageUseCase
from src.dependencies import get_stream_message_use_case
from src.domain.entities.stream_event import StreamEvent, StreamEventType
from src.domain.logging.messages import LogMessage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/api/v1/ws/{thread_id}")
async def websocket_chat(
    websocket: WebSocket,
    thread_id: str,
    use_case: Annotated[StreamMessageUseCase, Depends(get_stream_message_use_case)],
) -> None:
    await websocket.accept()
    logger.info(LogMessage.WS_CONNECTED, thread_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                logger.exception(LogMessage.WS_INVALID_JSON, thread_id, data[:200])
                await websocket.send_text(json.dumps({"error": "Invalid JSON"}))
                continue
            message = payload.get("message", "")
            logger.info(LogMessage.WS_MESSAGE_RECEIVED, thread_id, message[:80])
            chunk_count = 0
            try:
                async for event in use_case.execute(thread_id, message):
                    if event.type in (StreamEventType.THINKING, StreamEventType.CONTENT):
                        chunk_count += 1
                    await websocket.send_text(event.model_dump_json())
                await websocket.send_text("[END]")
                logger.info(LogMessage.WS_STREAM_COMPLETE, thread_id, chunk_count)
            except Exception as exc:
                logger.exception(LogMessage.WS_STREAM_ERROR, thread_id, chunk_count)
                error_event = StreamEvent(type=StreamEventType.ERROR, data=str(exc))
                await websocket.send_text(error_event.model_dump_json())
    except WebSocketDisconnect:
        logger.info(LogMessage.WS_DISCONNECTED, thread_id)
    except Exception:
        logger.exception(LogMessage.WS_UNEXPECTED_ERROR, thread_id)
