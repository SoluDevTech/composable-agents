"""API key security for the Composable Agents API.

Validates the ``X-API-Key`` header against the configured master key. When the
master key is empty (dev/test), authentication is disabled with a warning.

The dual-auth ``verify_credentials`` dependency delegates to an injected
:class:`~src.domain.services.auth.auth_service.AuthService` (JWT bearer token
+ per-user API key) and sets the RLS contextvars on success.

The WebSocket variant ``verify_credentials_ws`` accepts either
``Authorization: Bearer <jwt>`` or ``X-API-Key: <key>`` and rejects the
handshake with HTTP 401 on failure (sending a raw HTTP 401 response via the
ASGI ``websocket.http.response`` extension so the client receives a proper
Unauthorized status instead of the default 403).
"""

import json
import logging
import secrets

from fastapi import Depends, Request, WebSocket
from fastapi.security import APIKeyHeader

from src.domain.entities.auth.auth_context import AuthContext
from src.domain.errors.messages import ErrorMessage
from src.domain.errors.security import AuthenticationError, InvalidApiKeyError
from src.domain.services.auth.auth_service import AuthService
from src.infrastructure.database.rls_context import (
    current_auth_context,
    current_auth_method,
    current_credential,
    current_user_id,
)

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

    def __init__(self, master_key: str = "") -> None:
        self.master_key = master_key
        # Dual-auth service (JWT + per-user API key). Injected via
        # ``set_auth_service`` from the composition root; ``verify_credentials``
        # raises a clear RuntimeError if it is called before wiring.
        self._auth_service: AuthService | None = None

    def set_auth_service(self, auth_service: AuthService) -> None:
        """Inject the dual-auth :class:`AuthService`.

        Args:
            auth_service: The wired ``AuthService`` (JWT port + API key repo).
        """
        self._auth_service = auth_service

    def has_auth_service(self) -> bool:
        """Return whether a dual-auth :class:`AuthService` is wired."""
        return self._auth_service is not None

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

    async def verify_credentials(self, request: Request) -> AuthContext:
        """Dual-auth FastAPI dependency: JWT bearer token OR per-user API key.

        Reads the ``Authorization`` and ``X-API-Key`` headers, delegates to the
        injected :class:`AuthService`, raises :class:`AuthenticationError` (401)
        when no credential validates, and otherwise sets the RLS contextvars
        (``current_user_id`` / ``current_credential``) and returns the resolved
        :class:`AuthContext`.

        Args:
            request: The incoming FastAPI request (headers are read from it).

        Returns:
            The authenticated :class:`AuthContext`.

        Raises:
            RuntimeError: If ``set_auth_service`` was never called (misuse).
            AuthenticationError: If no credential could be validated (401).
        """
        if self._auth_service is None:
            raise RuntimeError("ComposableAgentsSecurity.verify_credentials called before set_auth_service")

        authorization = request.headers.get("authorization")
        api_key = request.headers.get("x-api-key")

        ctx = await self._auth_service.authenticate(
            authorization=authorization,
            api_key=api_key,
        )
        if ctx is None:
            raise AuthenticationError(ErrorMessage.AUTH_INVALID_CREDENTIALS)

        # Wire the RLS contextvars for downstream SQLAlchemy event listeners.
        current_user_id.set(ctx.user_id)
        current_credential.set(ctx.raw_credential)
        current_auth_method.set(ctx.method)
        current_auth_context.set(ctx)
        return ctx

    async def verify_credentials_ws(self, websocket: WebSocket) -> AuthContext | None:
        """Dual-auth WebSocket dependency: JWT bearer token OR per-user API key.

        Reads the ``Authorization`` and ``X-API-Key`` headers from the
        WebSocket handshake, delegates to the injected :class:`AuthService`,
        and on success sets the RLS contextvars and returns the
        :class:`AuthContext`. On failure, rejects the handshake with HTTP 401
        (via the ASGI ``websocket.http.response`` extension) and returns
        ``None`` so the caller can simply ``return`` from the endpoint.

        Unlike the HTTP variant, this NEVER raises — WebSocket endpoints
        cannot propagate an exception to a clean HTTP 401, so the rejection is
        sent inline and ``None`` is returned.

        Args:
            websocket: The incoming WebSocket connection.

        Returns:
            The authenticated :class:`AuthContext` on success, or ``None`` on
            failure (the handshake has already been rejected with 401).
        """
        if self._auth_service is None:
            # No dual-auth wired (dev/test, master-key only). Silent no-op so
            # the caller can fall back to the master-key path without a spurious
            # 401 having already been sent on the handshake.
            return None

        authorization = websocket.headers.get("authorization")
        api_key = websocket.headers.get("x-api-key")

        ctx = await self._auth_service.authenticate(
            authorization=authorization,
            api_key=api_key,
        )
        if ctx is None:
            await _reject_ws_with_401(websocket, str(ErrorMessage.AUTH_INVALID_CREDENTIALS))
            return None

        # Wire the RLS contextvars for downstream SQLAlchemy event listeners.
        current_user_id.set(ctx.user_id)
        current_credential.set(ctx.raw_credential)
        current_auth_method.set(ctx.method)
        current_auth_context.set(ctx)
        return ctx
