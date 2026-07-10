"""Tests for API key security (``ComposableAgentsSecurity``).

Unit tests call ``verify_api_key`` directly to cover each branch (disabled,
valid, missing, invalid). Integration tests build a minimal FastAPI app per
test with a controllable ``ComposableAgentsSecurity`` instance (no module-level
state to patch) and assert end-to-end behavior through the ASGI transport.
"""

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

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


# -- Unit tests ----------------------------------------------------------------


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


# -- Integration tests ----------------------------------------------------------


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
