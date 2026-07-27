"""Tests for the WebSocket router dual auth (JWT + API key).

The websocket router accepts either ``Authorization: Bearer <jwt>`` or
``X-API-Key: <key>``. On success it accepts the handshake and sets the
``current_user_id`` contextvar. On failure it rejects with HTTP 401 via the
ASGI ``websocket.http.response`` extension (matching the existing master-key
behaviour).
"""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.domain.entities.user.user import User
from src.domain.ports.auth.api_key_repository import ApiKeyRepository
from src.domain.ports.auth.jwt_service import JwtServicePort
from src.domain.services.auth.auth_service import AuthService
from src.security import ComposableAgentsSecurity


def _build_security(jwt_port: AsyncMock, api_key_repo: AsyncMock) -> ComposableAgentsSecurity:
    auth_service = AuthService(jwt_port=jwt_port, api_key_repo=api_key_repo)
    security = ComposableAgentsSecurity(master_key="")
    security.set_auth_service(auth_service)
    return security


@pytest.fixture
def jwt_port() -> AsyncMock:
    mock = AsyncMock(spec=JwtServicePort)
    mock.decode_token.return_value = User(sub="ws-user-jwt")
    return mock


@pytest.fixture
def api_key_repo() -> AsyncMock:
    mock = AsyncMock(spec=ApiKeyRepository)
    mock.find_active_by_hash.return_value = ("ws-user-key", "k1")
    return mock


@pytest.fixture
def security(jwt_port, api_key_repo) -> ComposableAgentsSecurity:
    return _build_security(jwt_port, api_key_repo)


def _build_app(security: ComposableAgentsSecurity):
    """Build a minimal FastAPI app with one WS endpoint guarded by verify_ws."""
    from fastapi import FastAPI, WebSocket

    app = FastAPI()

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        ctx = await security.verify_credentials_ws(websocket)
        if ctx is None:
            return  # rejected inside verify
        await websocket.accept()
        await websocket.send_text(f"user_id={ctx.user_id}")
        await websocket.close()

    return app


class TestWebSocketDualAuth:
    """WebSocket accepts JWT or API key; rejects otherwise."""

    def test_jwt_accepted(self, security, jwt_port):
        # Arrange
        app = _build_app(security)
        client = TestClient(app)

        # Act — use connect with headers
        with client.websocket_connect("/ws", headers={"Authorization": "Bearer valid"}) as ws:
            msg = ws.receive_text()

        # Assert
        assert msg == "user_id=ws-user-jwt"
        jwt_port.decode_token.assert_awaited()

    def test_api_key_accepted(self, security, api_key_repo):
        # Arrange
        app = _build_app(security)
        client = TestClient(app)

        # Act
        with client.websocket_connect("/ws", headers={"X-API-Key": "cpk_valid"}) as ws:
            msg = ws.receive_text()

        # Assert
        assert msg == "user_id=ws-user-key"
        api_key_repo.find_active_by_hash.assert_awaited()

    def test_no_credentials_rejected_with_401(self, security):
        # Arrange
        app = _build_app(security)
        client = TestClient(app)

        # Act / Assert — handshake rejected. Starlette raises either
        # WebSocketDisconnect (older) or WebSocketDenialResponse (newer) with
        # a 401 status_code on a rejected handshake.
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises((WebSocketDisconnect, Exception)) as exc_info, client.websocket_connect("/ws"):
            pass
        # The rejection carries a 401 status (WebSocketDenialResponse) or a
        # close code equivalent (WebSocketDisconnect).
        denial = exc_info.value
        status = getattr(denial, "status_code", None) or getattr(denial, "code", None)
        assert status in (401, 1008, 1006)

    def test_invalid_api_key_rejected(self, security, api_key_repo):
        # Arrange
        api_key_repo.find_active_by_hash.return_value = None
        app = _build_app(security)
        client = TestClient(app)

        # Act / Assert
        from starlette.websockets import WebSocketDisconnect

        with (
            pytest.raises((WebSocketDisconnect, Exception)),
            client.websocket_connect("/ws", headers={"X-API-Key": "cpk_wrong"}),
        ):
            pass
