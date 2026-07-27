"""Tests that ``verify_credentials`` sets the ``current_auth_method`` contextvar.

The dual-auth dependency sets three contextvars on success:

* ``current_user_id``     — the resolved user id.
* ``current_credential``   — the raw credential (JWT value or API key).
* ``current_auth_method``  — ``"jwt"`` or ``"api_key"`` matching the auth method.

The first two are already covered by ``test_verify_credentials.py``. This file
asserts the third (``current_auth_method``) is set correctly for both paths,
so MCP credential propagation (``${USER_JWT}`` / ``${USER_API_KEY}``) can read
the method downstream.
"""

from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from src.domain.entities.auth.auth_context import AuthContext
from src.domain.entities.user.user import User
from src.domain.errors.security import AuthenticationError
from src.domain.ports.auth.api_key_repository import ApiKeyRepository
from src.domain.ports.auth.jwt_service import JwtServicePort
from src.domain.services.auth.auth_service import AuthService
from src.infrastructure.database.rls_context import current_auth_method
from src.security import ComposableAgentsSecurity


def _build_security(jwt_port: AsyncMock, api_key_repo: AsyncMock) -> ComposableAgentsSecurity:
    auth_service = AuthService(jwt_port=jwt_port, api_key_repo=api_key_repo)
    security = ComposableAgentsSecurity(master_key="")
    security.set_auth_service(auth_service)  # type: ignore[attr-defined]
    return security


def _build_app(security: ComposableAgentsSecurity) -> FastAPI:
    """Build a minimal app that returns the ``current_auth_method`` contextvar."""
    app = FastAPI()

    @app.get("/protected")
    async def protected(ctx: AuthContext = Depends(security.verify_credentials)) -> dict:
        return {"user_id": ctx.user_id, "method": ctx.method, "method_ctx": current_auth_method.get()}

    @app.exception_handler(AuthenticationError)
    async def _auth_error_handler(_request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(status_code=int(exc.status_code), content={"detail": exc.detail})

    return app


class TestVerifyCredentialsSetsMethod:
    """``verify_credentials`` sets ``current_auth_method`` for downstream MCP propagation."""

    @pytest.fixture
    def jwt_port(self) -> AsyncMock:
        mock = AsyncMock(spec=JwtServicePort)
        mock.decode_token.return_value = User(sub="user-jwt-1", email="a@b.c")
        return mock

    @pytest.fixture
    def api_key_repo(self) -> AsyncMock:
        mock = AsyncMock(spec=ApiKeyRepository)
        mock.find_active_by_hash.return_value = ("user-api-1", "key-id-1")
        return mock

    @pytest.fixture
    def app(self, jwt_port, api_key_repo) -> FastAPI:
        security = _build_security(jwt_port, api_key_repo)
        return _build_app(security)

    async def test_jwt_path_sets_method_ctx_to_jwt(self, app: FastAPI) -> None:
        # Act
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/protected", headers={"Authorization": "Bearer valid"})

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert body["method"] == "jwt"
        assert body["method_ctx"] == "jwt"

    async def test_api_key_path_sets_method_ctx_to_api_key(self, app: FastAPI, jwt_port: AsyncMock) -> None:
        # Act
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/protected", headers={"X-API-Key": "cpk_valid"})

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert body["method"] == "api_key"
        assert body["method_ctx"] == "api_key"
