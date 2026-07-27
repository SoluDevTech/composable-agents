"""End-to-end tests for the ``verify_credentials`` FastAPI dependency.

Builds a minimal FastAPI app whose protected route depends on a
``verify_credentials`` callable. The dependency extracts the ``Authorization``
and ``X-API-Key`` headers, calls ``AuthService.authenticate``, raises
``AuthenticationError`` when no context is returned, and otherwise sets the
RLS contextvars and returns the ``AuthContext``.

The external boundaries (``JwtServicePort`` and ``ApiKeyRepository``) are
mocked via ``AsyncMock``; ``AuthService`` and the security wrapper are the
real internal implementations.
"""

from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from src.domain.entities.auth.auth_context import AuthContext
from src.domain.entities.user.user import User
from src.domain.errors.codes import ErrorCode
from src.domain.errors.messages import ErrorMessage
from src.domain.errors.security import AuthenticationError
from src.domain.ports.auth.api_key_repository import ApiKeyRepository
from src.domain.ports.auth.jwt_service import JwtServicePort
from src.domain.services.auth.auth_service import AuthService
from src.security import ComposableAgentsSecurity


def _build_security(
    jwt_port: AsyncMock,
    api_key_repo: AsyncMock,
) -> ComposableAgentsSecurity:
    """Wire a real ``ComposableAgentsSecurity`` with a real ``AuthService``.

    The ports are ``AsyncMock``s (external boundaries); the security wrapper
    and the auth service are real internal implementations.
    """
    auth_service = AuthService(jwt_port=jwt_port, api_key_repo=api_key_repo)
    security = ComposableAgentsSecurity(master_key="")
    security.set_auth_service(auth_service)  # type: ignore[attr-defined]
    return security


def _build_app(security: ComposableAgentsSecurity) -> FastAPI:
    """Build a minimal FastAPI app with one ``verify_credentials``-protected route."""
    app = FastAPI()

    @app.get("/protected")
    async def protected(ctx: AuthContext = Depends(security.verify_credentials)) -> dict:
        return {"user_id": ctx.user_id, "method": ctx.method}

    @app.exception_handler(AuthenticationError)
    async def _auth_error_handler(_request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(status_code=int(exc.status_code), content={"detail": exc.detail})

    return app


class TestVerifyCredentialsJwt:
    """End-to-end tests for the JWT path of ``verify_credentials``."""

    @pytest.fixture
    def jwt_port(self) -> AsyncMock:
        mock = AsyncMock(spec=JwtServicePort)
        mock.decode_token.return_value = User(sub="user-jwt-1", email="a@b.c")
        return mock

    @pytest.fixture
    def api_key_repo(self) -> AsyncMock:
        return AsyncMock(spec=ApiKeyRepository)

    @pytest.fixture
    def app(self, jwt_port, api_key_repo) -> FastAPI:
        security = _build_security(jwt_port, api_key_repo)
        return _build_app(security)

    async def test_valid_jwt_returns_200_and_user_id(self, app: FastAPI):
        # Arrange
        transport = ASGITransport(app=app)

        # Act
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/protected", headers={"Authorization": "Bearer valid"})

        # Assert
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "user-jwt-1"
        assert resp.json()["method"] == "jwt"

    async def test_invalid_jwt_returns_401(self, app: FastAPI, jwt_port: AsyncMock):
        # Arrange
        jwt_port.decode_token.return_value = None
        transport = ASGITransport(app=app)

        # Act
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/protected", headers={"Authorization": "Bearer bogus"})

        # Assert
        assert resp.status_code == 401
        assert resp.json()["detail"] == str(ErrorMessage.AUTH_INVALID_CREDENTIALS)


class TestVerifyCredentialsApiKey:
    """End-to-end tests for the API-key path of ``verify_credentials``."""

    @pytest.fixture
    def jwt_port(self) -> AsyncMock:
        return AsyncMock(spec=JwtServicePort)

    @pytest.fixture
    def api_key_repo(self) -> AsyncMock:
        mock = AsyncMock(spec=ApiKeyRepository)
        mock.find_active_by_hash.return_value = ("user-api-1", "key-id-1")
        return mock

    @pytest.fixture
    def app(self, jwt_port, api_key_repo) -> FastAPI:
        security = _build_security(jwt_port, api_key_repo)
        return _build_app(security)

    async def test_valid_api_key_returns_200(self, app: FastAPI):
        # Arrange
        transport = ASGITransport(app=app)

        # Act
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/protected", headers={"X-API-Key": "cpk_valid"})

        # Assert
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "user-api-1"
        assert resp.json()["method"] == "api_key"

    async def test_wrong_api_key_returns_401(self, app: FastAPI, api_key_repo: AsyncMock):
        # Arrange
        api_key_repo.find_active_by_hash.return_value = None
        transport = ASGITransport(app=app)

        # Act
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/protected", headers={"X-API-Key": "cpk_wrong"})

        # Assert
        assert resp.status_code == 401
        assert resp.json()["detail"] == str(ErrorMessage.AUTH_INVALID_CREDENTIALS)


class TestVerifyCredentialsMissing:
    """End-to-end test with no credentials at all."""

    @pytest.fixture
    def jwt_port(self) -> AsyncMock:
        return AsyncMock(spec=JwtServicePort)

    @pytest.fixture
    def api_key_repo(self) -> AsyncMock:
        return AsyncMock(spec=ApiKeyRepository)

    @pytest.fixture
    def app(self, jwt_port, api_key_repo) -> FastAPI:
        security = _build_security(jwt_port, api_key_repo)
        return _build_app(security)

    async def test_no_credentials_returns_401(self, app: FastAPI):
        # Arrange
        transport = ASGITransport(app=app)

        # Act
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/protected")

        # Assert
        assert resp.status_code == 401
        assert resp.json()["detail"] == str(ErrorMessage.AUTH_INVALID_CREDENTIALS)


class TestAuthenticationErrorStatusCode:
    """Unit test for the ``AuthenticationError`` status code."""

    def test_authentication_error_status_code_is_401(self) -> None:
        # Act
        error = AuthenticationError(ErrorMessage.AUTH_INVALID_CREDENTIALS)

        # Assert
        assert int(error.status_code) == ErrorCode.UNAUTHORIZED
