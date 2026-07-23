"""Tests for API key security (``ComposableAgentsSecurity``).

Unit tests call ``verify_api_key`` and ``verify_api_key_ws`` directly to cover
each branch (disabled, valid, missing, invalid). Integration tests build a
minimal FastAPI app per test with a controllable ``ComposableAgentsSecurity``
instance (no module-level state to patch) and assert end-to-end behavior
through the ASGI transport — including WebSocket handshake rejection.
"""

import json
from typing import Any

import pytest
from fastapi import APIRouter, Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from starlette.testclient import WebSocketDenialResponse

from src.domain.errors.codes import ErrorCode
from src.domain.errors.messages import ErrorMessage
from src.domain.errors.security import InvalidApiKeyError
from src.security import ComposableAgentsSecurity

_MASTER_KEY = "super-secret-key"


# -- Helpers -------------------------------------------------------------------


def _build_app(master_key: str) -> FastAPI:
    """Build a minimal FastAPI app with a public health route and one protected route.

    The protected router mirrors the real wiring in ``src.main``: a single
    ``ComposableAgentsSecurity`` instance whose ``verify_api_key`` is applied
    as a router-level dependency. A dedicated exception handler maps
    ``InvalidApiKeyError`` to its declared status code + detail, matching the
    production handler shape.
    """
    security = ComposableAgentsSecurity(master_key=master_key)

    health = APIRouter()

    @health.get("/health")
    async def health_check() -> dict:
        return {"status": "ok"}

    protected = APIRouter(dependencies=[Depends(security.verify_api_key)])

    @protected.get("/api/v1/threads")
    async def list_threads() -> list:
        return []

    app = FastAPI()
    app.include_router(health)
    app.include_router(protected)

    @app.exception_handler(InvalidApiKeyError)
    async def _invalid_api_key_handler(_request, exc: InvalidApiKeyError) -> JSONResponse:
        return JSONResponse(status_code=int(exc.status_code), content={"detail": exc.detail})

    return app


def _build_ws_app(master_key: str) -> FastAPI:
    """Build a minimal FastAPI app with a WebSocket endpoint guarded by ``verify_api_key_ws``.

    Mirrors the real wiring in ``src/application/routes/websocket.py``: the
    security instance is injected via ``Depends(get_security)`` and called
    before ``websocket.accept()``.
    """
    security = ComposableAgentsSecurity(master_key=master_key)

    app = FastAPI()

    @app.websocket("/api/v1/ws/{thread_id}")
    async def ws_endpoint(
        websocket: WebSocket,
        thread_id: str,
    ) -> None:
        key = await security.verify_api_key_ws(websocket)
        if not key and security.master_key:
            # Rejected via HTTP 401 — verify_api_key_ws already sent the response.
            return
        await websocket.accept()
        await websocket.send_text(json.dumps({"status": "connected", "thread_id": thread_id}))
        try:
            while True:
                data = await websocket.receive_text()
                await websocket.send_text(json.dumps({"echo": data}))
        except WebSocketDisconnect:
            pass

    return app


class _FakeWebSocket:
    """Minimal WebSocket mock for unit-testing ``verify_api_key_ws`` directly.

    Records ASGI messages sent by ``_reject_ws_with_401`` so we can assert
    the status code and body without spinning up a full server.
    """

    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}
        self.sent_messages: list[dict[str, Any]] = []

    async def send(self, message: dict[str, Any]) -> None:
        self.sent_messages.append(message)


# -- Unit tests (verify_api_key — HTTP) ----------------------------------------


class TestVerifyApiKey:
    """Direct unit tests for ``ComposableAgentsSecurity.verify_api_key``."""

    async def test_verify_api_key_disabled_when_master_key_empty(self, caplog):
        # Arrange
        security = ComposableAgentsSecurity(master_key="")

        # Act
        result = await security.verify_api_key(api_key_header="anything")

        # Assert
        assert result == ""
        assert any(
            ErrorMessage.API_KEY_DISABLED in record.message
            for record in caplog.records
            if record.name == "src.security"
        )

    async def test_verify_api_key_returns_key_when_valid(self):
        # Arrange
        security = ComposableAgentsSecurity(master_key=_MASTER_KEY)

        # Act
        result = await security.verify_api_key(api_key_header=_MASTER_KEY)

        # Assert
        assert result == _MASTER_KEY

    async def test_verify_api_key_raises_when_missing(self):
        # Arrange
        security = ComposableAgentsSecurity(master_key=_MASTER_KEY)

        # Act & Assert
        with pytest.raises(InvalidApiKeyError, match=str(ErrorMessage.API_KEY_EMPTY)):
            await security.verify_api_key(api_key_header=None)

    async def test_verify_api_key_raises_when_invalid(self):
        # Arrange
        security = ComposableAgentsSecurity(master_key=_MASTER_KEY)

        # Act & Assert
        with pytest.raises(InvalidApiKeyError, match=str(ErrorMessage.API_KEY_UNAUTHORIZED)):
            await security.verify_api_key(api_key_header="wrong-key")

    async def test_invalid_api_key_error_status_code_is_401(self):
        # Arrange
        error = InvalidApiKeyError(ErrorMessage.API_KEY_UNAUTHORIZED)

        # Act & Assert
        assert int(error.status_code) == ErrorCode.UNAUTHORIZED


# -- Unit tests (verify_api_key_ws — WebSocket) --------------------------------


class TestVerifyApiKeyWs:
    """Direct unit tests for ``ComposableAgentsSecurity.verify_api_key_ws``.

    Covers the four branches of the WebSocket guard:
    1. master_key empty → disabled, returns ""
    2. valid key → returns key
    3. missing key → sends HTTP 401 via ASGI extension
    4. wrong key → sends HTTP 401 via ASGI extension
    """

    async def test_verify_api_key_ws_disabled_when_master_key_empty(self, caplog):
        # Arrange
        security = ComposableAgentsSecurity(master_key="")
        ws = _FakeWebSocket(headers={"x-api-key": "anything"})

        # Act
        result = await security.verify_api_key_ws(websocket=ws)  # type: ignore[arg-type]

        # Assert
        assert result == ""
        assert ws.sent_messages == []  # no rejection sent — auth disabled
        assert any(
            ErrorMessage.API_KEY_DISABLED in record.message
            for record in caplog.records
            if record.name == "src.security"
        )

    async def test_verify_api_key_ws_returns_key_when_valid(self):
        # Arrange
        security = ComposableAgentsSecurity(master_key=_MASTER_KEY)
        ws = _FakeWebSocket(headers={"x-api-key": _MASTER_KEY})

        # Act
        result = await security.verify_api_key_ws(websocket=ws)  # type: ignore[arg-type]

        # Assert
        assert result == _MASTER_KEY
        assert ws.sent_messages == []  # no rejection — connection accepted

    async def test_verify_api_key_ws_sends_401_when_missing(self, caplog):
        # Arrange
        security = ComposableAgentsSecurity(master_key=_MASTER_KEY)
        ws = _FakeWebSocket(headers={})

        # Act
        result = await security.verify_api_key_ws(websocket=ws)  # type: ignore[arg-type]

        # Assert
        assert result == ""
        assert len(ws.sent_messages) == 2  # response.start + response.body
        assert ws.sent_messages[0]["type"] == "websocket.http.response.start"
        assert ws.sent_messages[0]["status"] == 401
        assert ws.sent_messages[1]["type"] == "websocket.http.response.body"
        body = json.loads(ws.sent_messages[1]["body"])
        assert body["detail"] == str(ErrorMessage.API_KEY_EMPTY)
        assert any(
            ErrorMessage.API_KEY_EMPTY in record.message for record in caplog.records if record.name == "src.security"
        )

    async def test_verify_api_key_ws_sends_401_when_invalid(self, caplog):
        # Arrange
        security = ComposableAgentsSecurity(master_key=_MASTER_KEY)
        ws = _FakeWebSocket(headers={"x-api-key": "wrong-key"})

        # Act
        result = await security.verify_api_key_ws(websocket=ws)  # type: ignore[arg-type]

        # Assert
        assert result == ""
        assert ws.sent_messages[0]["status"] == 401
        body = json.loads(ws.sent_messages[1]["body"])
        assert body["detail"] == str(ErrorMessage.API_KEY_UNAUTHORIZED)
        assert any(
            ErrorMessage.API_KEY_UNAUTHORIZED in record.message
            for record in caplog.records
            if record.name == "src.security"
        )


# -- Integration tests (HTTP) ---------------------------------------------------


class TestApiKeyIntegration:
    """End-to-end tests through a minimal FastAPI app + httpx ASGI client."""

    async def test_health_endpoint_public_without_key(self):
        # Arrange
        app = _build_app(master_key=_MASTER_KEY)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Act
            resp = await client.get("/health")

            # Assert
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}

    async def test_protected_route_returns_401_without_key(self):
        # Arrange
        app = _build_app(master_key=_MASTER_KEY)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Act
            resp = await client.get("/api/v1/threads")

            # Assert
            assert resp.status_code == 401
            assert resp.json()["detail"] == str(ErrorMessage.API_KEY_EMPTY)

    async def test_protected_route_returns_401_with_invalid_key(self):
        # Arrange
        app = _build_app(master_key=_MASTER_KEY)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Act
            resp = await client.get(
                "/api/v1/threads",
                headers={"X-API-Key": "wrong-key"},
            )

            # Assert
            assert resp.status_code == 401
            assert resp.json()["detail"] == str(ErrorMessage.API_KEY_UNAUTHORIZED)

    async def test_protected_route_accessible_with_valid_key(self):
        # Arrange
        app = _build_app(master_key=_MASTER_KEY)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Act
            resp = await client.get(
                "/api/v1/threads",
                headers={"X-API-Key": _MASTER_KEY},
            )

            # Assert
            assert resp.status_code == 200
            assert resp.json() == []

    async def test_protected_route_accessible_when_auth_disabled(self):
        # Arrange — empty master key disables auth (dev/test mode)
        app = _build_app(master_key="")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Act
            resp = await client.get("/api/v1/threads")

            # Assert
            assert resp.status_code == 200
            assert resp.json() == []


# -- Integration tests (WebSocket) ---------------------------------------------


class TestApiKeyWsIntegration:
    """End-to-end WebSocket tests through a minimal FastAPI app + TestClient.

    Uses Starlette's ``TestClient.websocket_connect`` which supports the
    ``websocket.http.response`` extension, allowing us to assert the HTTP 401
    rejection status during the handshake.
    """

    def test_ws_handshake_without_key_rejected_with_401(self):
        # Arrange
        app = _build_ws_app(master_key=_MASTER_KEY)
        client = TestClient(app)

        # Act & Assert — TestClient raises WebSocketDenialResponse with HTTP status
        with pytest.raises(WebSocketDenialResponse) as exc_info, client.websocket_connect("/api/v1/ws/test"):
            pass
        assert exc_info.value.status_code == 401
        body = exc_info.value.json()
        assert body["detail"] == str(ErrorMessage.API_KEY_EMPTY)

    def test_ws_handshake_with_wrong_key_rejected_with_401(self):
        # Arrange
        app = _build_ws_app(master_key=_MASTER_KEY)
        client = TestClient(app)

        # Act & Assert
        with pytest.raises(WebSocketDenialResponse) as exc_info:  # noqa: SIM117
            with client.websocket_connect("/api/v1/ws/test", headers={"X-API-Key": "wrong"}):
                pass
        assert exc_info.value.status_code == 401
        body = exc_info.value.json()
        assert body["detail"] == str(ErrorMessage.API_KEY_UNAUTHORIZED)

    def test_ws_handshake_with_valid_key_connects(self):
        # Arrange
        app = _build_ws_app(master_key=_MASTER_KEY)
        client = TestClient(app)

        # Act
        with client.websocket_connect("/api/v1/ws/test", headers={"X-API-Key": _MASTER_KEY}) as ws:
            # Assert
            data = json.loads(ws.receive_text())
            assert data["status"] == "connected"
            assert data["thread_id"] == "test"

    def test_ws_handshake_when_auth_disabled_connects_without_key(self):
        # Arrange — empty master key disables auth (dev/test mode)
        app = _build_ws_app(master_key="")
        client = TestClient(app)

        # Act
        with client.websocket_connect("/api/v1/ws/test") as ws:
            # Assert — connection accepted without X-API-Key header
            data = json.loads(ws.receive_text())
            assert data["status"] == "connected"
