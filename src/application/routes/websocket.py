import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from src.application.use_cases.stream_message import StreamMessageUseCase
from src.dependencies import get_stream_message_use_case

router = APIRouter(tags=["websocket"])


@router.websocket("/api/v1/ws/{thread_id}")
async def websocket_chat(
    websocket: WebSocket,
    thread_id: str,
    use_case: StreamMessageUseCase = Depends(get_stream_message_use_case),
) -> None:
    """WebSocket endpoint for streaming chat messages.

    Receives JSON messages with a 'message' field and streams back
    individual text chunks as the agent responds.

    Args:
        websocket: The WebSocket connection.
        thread_id: The conversation thread identifier.
        use_case: Injected StreamMessageUseCase.
    """
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            message = payload.get("message", "")
            async for chunk in use_case.execute(thread_id, message):
                await websocket.send_text(chunk)
            await websocket.send_text("[END]")
    except WebSocketDisconnect:
        pass
