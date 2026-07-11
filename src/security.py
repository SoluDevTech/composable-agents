"""API key security for the Composable Agents API.

Validates the ``X-API-Key`` header against the configured master key. When the
master key is empty (dev/test), authentication is disabled with a warning.
"""

import logging
import secrets

from fastapi import Depends, WebSocket
from fastapi.security import APIKeyHeader

from src.domain.errors.messages import ErrorMessage
from src.domain.errors.security import InvalidApiKeyError

logger = logging.getLogger(__name__)


async def _reject_ws_with_401(websocket: WebSocket, reason: str) -> None:
    """Reject a WebSocket handshake with HTTP 401.

    Sends a raw HTTP 401 response via the ASGI ``websocket.http.response``
    extension so the client receives a proper Unauthorized status instead
    of the default 403 that uvicorn maps from ``websocket.close``.

    Args:
        websocket: The incoming WebSocket connection to reject.
        reason: The error detail to include in the JSON response body.
    """
    import json

    body = json.dumps({"detail": reason}).encode("utf-8")
    await websocket.send(
        {
            "type": "websocket.http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await websocket.send(
        {
            "type": "websocket.http.response.body",
            "body": body,
        }
    )


class ComposableAgentsSecurity:
    """Validates incoming API keys against the configured master key.

    The class is instantiated once at the composition root with the master key
    (``settings.api_key``) and its ``verify_api_key`` method is injected as a
    FastAPI dependency on protected routers. When the master key is empty the
    check is bypassed (useful for local dev/test).

    For WebSocket endpoints — which do not inherit ``APIRouter(dependencies=...)``
    — call ``verify_api_key_ws`` explicitly inside the endpoint.
    """

    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    def __init__(self, master_key: str) -> None:
        self.master_key = master_key

    async def verify_api_key(
        self,
        api_key_header: str | None = Depends(api_key_header),
    ) -> str:
        """Validate the ``X-API-Key`` header against ``master_key``.

        Args:
            api_key_header: The value of the ``X-API-Key`` request header.

        Returns:
            The validated API key string, or an empty string when auth is
            disabled (no master key configured).

        Raises:
            InvalidApiKeyError: If the header is missing or does not match the
                master key.
        """
        if not self.master_key:  # auth disabled (dev/test)
            logger.warning(ErrorMessage.API_KEY_DISABLED)
            return ""
        if not api_key_header:
            raise InvalidApiKeyError(ErrorMessage.API_KEY_EMPTY)
        if not secrets.compare_digest(api_key_header, self.master_key):
            raise InvalidApiKeyError(ErrorMessage.API_KEY_UNAUTHORIZED)
        return api_key_header

    async def verify_api_key_ws(
        self,
        websocket: WebSocket,
    ) -> str:
        """Validate the ``X-API-Key`` header for a WebSocket connection.

        Unlike ``verify_api_key`` (HTTP), this sends a raw HTTP 401 response
        before the WebSocket upgrade so the client receives a proper
        Unauthorized status (uvicorn maps ``websocket.close`` to 403, which
        is semantically wrong for an auth failure).

        Args:
            websocket: The incoming WebSocket connection.

        Returns:
            The validated API key string, or an empty string when auth is
            disabled (no master key configured).
        """
        if not self.master_key:  # auth disabled (dev/test)
            logger.warning(ErrorMessage.API_KEY_DISABLED)
            return ""
        api_key = websocket.headers.get("x-api-key")
        if not api_key:
            logger.error(ErrorMessage.API_KEY_EMPTY)
            await _reject_ws_with_401(websocket, str(ErrorMessage.API_KEY_EMPTY))
            return ""
        if not secrets.compare_digest(api_key, self.master_key):
            logger.error(ErrorMessage.API_KEY_UNAUTHORIZED)
            await _reject_ws_with_401(websocket, str(ErrorMessage.API_KEY_UNAUTHORIZED))
            return ""
        return api_key
