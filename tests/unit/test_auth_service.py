"""Tests for the ``AuthService`` domain service.

``AuthService`` orchestrates dual authentication (JWT bearer token vs API key)
and is the only component that knows the precedence rules between the two. It
depends on a ``JwtServicePort`` (external JWKS boundary → mocked) and an
``ApiKeyRepository`` port (implemented in a later layer → mocked here per spec).

Tests cover:
- JWT path (valid token → AuthContext with method=jwt)
- JWT invalid (decode_token returns None → authenticate returns None)
- JWT missing prefix falls through (no api_key → None)
- API key path (valid hash lookup → AuthContext with method=api_key)
- API key revoked/unknown → None
- Both None → None
- JWT takes precedence over API key when both present
"""

import hashlib
from unittest.mock import AsyncMock

import pytest

from src.domain.entities.auth.auth_context import AuthContext
from src.domain.entities.user.user import User
from src.domain.ports.auth.api_key_repository import ApiKeyRepository
from src.domain.ports.auth.jwt_service import JwtServicePort
from src.domain.services.auth.auth_service import AuthService


class TestAuthServiceJwtPath:
    """Tests for the JWT bearer token authentication path."""

    @pytest.fixture
    def jwt_port(self) -> AsyncMock:
        mock = AsyncMock(spec=JwtServicePort)
        mock.decode_token.return_value = User(sub="user-123", email="a@b.c")
        return mock

    @pytest.fixture
    def api_key_repo(self) -> AsyncMock:
        return AsyncMock(spec=ApiKeyRepository)

    @pytest.fixture
    def auth_service(self, jwt_port, api_key_repo) -> AuthService:
        return AuthService(jwt_port=jwt_port, api_key_repo=api_key_repo)

    async def test_jwt_valid_returns_auth_context_with_jwt_method(self, auth_service, jwt_port):
        # Act
        result = await auth_service.authenticate(authorization="Bearer tok", api_key=None)

        # Assert
        assert result is not None
        assert isinstance(result, AuthContext)
        assert result.user_id == "user-123"
        assert result.method == "jwt"
        assert result.raw_credential == "tok"
        jwt_port.decode_token.assert_awaited_once_with("tok")

    async def test_jwt_valid_propagates_profile_claims(self, auth_service, jwt_port):
        # Arrange — IdP returns a fully populated User
        jwt_port.decode_token.return_value = User(
            sub="user-123",
            email="jane@example.com",
            name="Jane Doe",
            username="jane",
        )

        # Act
        result = await auth_service.authenticate(authorization="Bearer tok", api_key=None)

        # Assert — email / name / username propagated to the AuthContext
        assert result is not None
        assert result.email == "jane@example.com"
        assert result.name == "Jane Doe"
        assert result.username == "jane"

    async def test_jwt_valid_with_missing_optional_claims_yields_none_profile(self, auth_service, jwt_port):
        # Arrange — IdP returns only the required ``sub`` claim
        jwt_port.decode_token.return_value = User(sub="user-123")

        # Act
        result = await auth_service.authenticate(authorization="Bearer tok", api_key=None)

        # Assert — optional profile fields are None, not defaulted
        assert result is not None
        assert result.email is None
        assert result.name is None
        assert result.username is None

    async def test_jwt_invalid_returns_none(self, auth_service, jwt_port):
        # Arrange
        jwt_port.decode_token.return_value = None

        # Act
        result = await auth_service.authenticate(authorization="Bearer tok", api_key=None)

        # Assert
        assert result is None

    async def test_jwt_missing_prefix_falls_through_to_none(self, auth_service):
        # Arrange — "Token x" does not start with "Bearer "
        # Act
        result = await auth_service.authenticate(authorization="Token x", api_key=None)

        # Assert
        assert result is None


class TestAuthServiceApiKeyPath:
    """Tests for the X-API-Key authentication path."""

    @pytest.fixture
    def jwt_port(self) -> AsyncMock:
        return AsyncMock(spec=JwtServicePort)

    @pytest.fixture
    def api_key_repo(self) -> AsyncMock:
        mock = AsyncMock(spec=ApiKeyRepository)
        mock.find_active_by_hash.return_value = ("user-456", "key-id-1")
        return mock

    @pytest.fixture
    def auth_service(self, jwt_port, api_key_repo) -> AuthService:
        return AuthService(jwt_port=jwt_port, api_key_repo=api_key_repo)

    async def test_api_key_valid_returns_auth_context_with_api_key_method(self, auth_service, api_key_repo):
        # Arrange
        api_key = "cpk_xxx"

        # Act
        result = await auth_service.authenticate(authorization=None, api_key=api_key)

        # Assert
        assert result is not None
        assert isinstance(result, AuthContext)
        assert result.user_id == "user-456"
        assert result.method == "api_key"
        assert result.raw_credential == api_key
        # API-key auth never carries profile claims (no JWT to decode).
        assert result.email is None
        assert result.name is None
        assert result.username is None
        expected_hash = hashlib.sha256(api_key.encode()).hexdigest()
        api_key_repo.find_active_by_hash.assert_awaited_once_with(expected_hash)

    async def test_api_key_revoked_or_unknown_returns_none(self, auth_service, api_key_repo):
        # Arrange
        api_key_repo.find_active_by_hash.return_value = None

        # Act
        result = await auth_service.authenticate(authorization=None, api_key="cpk_wrong")

        # Assert
        assert result is None

    async def test_api_key_lookup_uses_sha256_hex_of_plaintext(self, auth_service, api_key_repo):
        # Arrange
        api_key = "cpk_lookup-test"

        # Act
        await auth_service.authenticate(authorization=None, api_key=api_key)

        # Assert
        called_hash = api_key_repo.find_active_by_hash.await_args.args[0]
        assert called_hash == hashlib.sha256(api_key.encode()).hexdigest()
        assert len(called_hash) == 64


class TestAuthServicePrecedenceAndEmpty:
    """Tests for precedence rules and the empty-credentials case."""

    @pytest.fixture
    def jwt_port(self) -> AsyncMock:
        mock = AsyncMock(spec=JwtServicePort)
        mock.decode_token.return_value = User(sub="user-jwt")
        return mock

    @pytest.fixture
    def api_key_repo(self) -> AsyncMock:
        mock = AsyncMock(spec=ApiKeyRepository)
        mock.find_active_by_hash.return_value = ("user-api", "key-id-1")
        return mock

    @pytest.fixture
    def auth_service(self, jwt_port, api_key_repo) -> AuthService:
        return AuthService(jwt_port=jwt_port, api_key_repo=api_key_repo)

    async def test_both_none_returns_none(self, auth_service):
        # Act
        result = await auth_service.authenticate(authorization=None, api_key=None)

        # Assert
        assert result is None

    async def test_jwt_takes_precedence_over_api_key(self, auth_service, jwt_port, api_key_repo):
        # Arrange — both Authorization: Bearer and X-API-Key present

        # Act
        result = await auth_service.authenticate(authorization="Bearer tok", api_key="cpk_xxx")

        # Assert
        assert result is not None
        assert result.method == "jwt"
        assert result.user_id == "user-jwt"
        jwt_port.decode_token.assert_awaited_once()
        api_key_repo.find_active_by_hash.assert_not_awaited()
