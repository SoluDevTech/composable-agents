import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from src.application.use_cases.stream_message import StreamMessageUseCase
from src.dependencies import get_stream_message_use_case
from src.domain.entities.message import Message

logger = logging.getLogger("composable-agents")

router = APIRouter(tags=["websocket"])


@router.websocket("/api/v1/ws/{thread_id}")
async def websocket_chat(
    websocket: WebSocket,
    thread_id: str,
    use_case: StreamMessageUseCase = Depends(get_stream_message_use_case),
) -> None:
    await websocket.accept()
    logger.info("[thread=%s] WebSocket connected", thread_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                logger.error("[thread=%s] Invalid JSON received: %s", thread_id, data[:200])
                await websocket.send_text(json.dumps({"error": "Invalid JSON"}))
                continue
            message = payload.get("message", "")
            logger.info("[thread=%s] WS message received: %s", thread_id, message[:80])
            chunk_count = 0
            try:
                async for event in use_case.execute(thread_id, message):
                    if isinstance(event, str):
                        chunk_count += 1
                        await websocket.send_text(event)
                    elif isinstance(event, Message):
                        await websocket.send_text(json.dumps({"type": "message", **event.model_dump(mode="json")}))
                await websocket.send_text("[END]")
                logger.info("[thread=%s] WS stream complete, %d chunks", thread_id, chunk_count)
            except Exception:
                logger.exception("[thread=%s] WS stream error after %d chunks", thread_id, chunk_count)
                await websocket.send_text(json.dumps({"error": "Agent execution error"}))
    except WebSocketDisconnect:
        logger.info("[thread=%s] WebSocket disconnected", thread_id)
    except Exception:
        logger.exception("[thread=%s] WebSocket unexpected error", thread_id)
