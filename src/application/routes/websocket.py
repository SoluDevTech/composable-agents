"""WebSocket chat route: streams TraceEvents then ``[END]``.

Emits TraceEvent records (not the legacy StreamEvent). On error, emits a plain
JSON error payload ``{"type": "error", "data": "..."}`` that is NOT a
TraceEvent (TraceEventType has no ERROR variant), matching the previous
contract.
"""

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from src.application.use_cases.stream_message import StreamMessageUseCase
from src.dependencies import get_security, get_stream_message_use_case
from src.domain.logging.messages import LogMessage
from src.security import ComposableAgentsSecurity

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/api/v1/ws/{thread_id}")
async def websocket_chat(
    websocket: WebSocket,
    thread_id: str,
    security: Annotated[ComposableAgentsSecurity, Depends(get_security)],
    use_case: Annotated[StreamMessageUseCase, Depends(get_stream_message_use_case)],
) -> None:
    """Stream TraceEvents over a WebSocket for each received message.

    For each received text payload ``{"message": "..."}``, emits one
    ``TraceEvent.model_dump_json()`` frame per event, then an ``[END]`` frame.
    On error, emits ``{"type": "error", "data": "..."}`` (not a TraceEvent).

    Args:
        websocket: The incoming WebSocket connection.
        thread_id: Conversation thread identifier.
        security: Security validator (API key check at handshake).
        use_case: StreamMessageUseCase wired with real repositories + mock runner.
    """
    # Dual-auth: JWT bearer token OR per-user API key. verify_credentials_ws
    # rejects the handshake with HTTP 401 on failure and returns None; the
    # master-key verify_api_key_ws is kept as a backward-compat fallback ONLY
    # when no auth service is wired (dev/test without dual auth). When dual
    # auth is wired, a 401 from verify_credentials_ws is final — we must NOT
    # call websocket.accept() on an already-rejected handshake.
    ctx = await security.verify_credentials_ws(websocket)
    if ctx is None:
        if security.has_auth_service():
            # Dual auth wired: verify_credentials_ws already rejected with 401.
            return
        # No dual auth wired (master-key only): fall back to the master key.
        key = await security.verify_api_key_ws(websocket)
        if not key and security.master_key:
            # Master-key auth enabled and the key was invalid — already rejected.
            return
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
            event_count = 0
            try:
                async for event in use_case.execute(thread_id, message):
                    event_count += 1
                    await websocket.send_text(event.model_dump_json())
                await websocket.send_text("[END]")
                logger.info(LogMessage.WS_STREAM_COMPLETE, thread_id, event_count)
            except Exception as exc:
                logger.exception(LogMessage.WS_STREAM_ERROR, thread_id, event_count)
                await websocket.send_text(json.dumps({"type": "error", "data": str(exc)}))
    except WebSocketDisconnect:
        logger.info(LogMessage.WS_DISCONNECTED, thread_id)
    except Exception:
        logger.exception(LogMessage.WS_UNEXPECTED_ERROR, thread_id)
