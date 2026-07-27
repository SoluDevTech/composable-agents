"""Auth domain service — orchestrates dual authentication.

The only component that knows the precedence rules between JWT bearer tokens
and per-user API keys. Depends on two ports (no concrete adapters):
``JwtServicePort`` (JWT verification) and ``ApiKeyRepository`` (API key
lookup). API keys are hashed (SHA-256) before lookup — plaintext is never
sent to the repository.

Precedence: JWT bearer token first; only when no valid JWT is present does the
service fall back to the API key path. When neither yields a context, the
service returns ``None`` and the caller (the FastAPI dependency) raises
``AuthenticationError``.
"""

import logging

from src.domain.entities.auth.auth_context import AuthContext
from src.domain.entities.user.user import User
from src.domain.logging.messages import LogMessage
from src.domain.ports.auth.api_key_repository import ApiKeyRepository
from src.domain.ports.auth.jwt_service import JwtServicePort
from src.domain.services.auth.api_key_hasher import ApiKeyHasher

logger = logging.getLogger(__name__)

_BEARER_PREFIX = "Bearer "


class AuthService:
    """Resolve an :class:`AuthContext` from a request's credentials.

    Args:
        jwt_port: Outbound port used to verify JWT bearer tokens.
        api_key_repo: Outbound port used to look up active API keys by hash.
    """

    def __init__(self, jwt_port: JwtServicePort, api_key_repo: ApiKeyRepository) -> None:
        self._jwt_port = jwt_port
        self._api_key_repo = api_key_repo

    async def authenticate(
        self,
        authorization: str | None,
        api_key: str | None,
    ) -> AuthContext | None:
        """Authenticate the request and return an :class:`AuthContext` or ``None``.

        Args:
            authorization: Raw value of the ``Authorization`` header (``None``
                if absent). Only the ``Bearer`` scheme is recognised.
            api_key: Raw value of the ``X-API-Key`` header (``None`` if absent).

        Returns:
            An :class:`AuthContext` on success, or ``None`` when no credential
            could be validated.

        Note:
            JWT takes precedence over API key: when a valid ``Bearer`` token is
            present the API key is never consulted.
        """
        # 1. JWT path — takes precedence.
        if authorization and authorization.startswith(_BEARER_PREFIX):
            token = authorization[len(_BEARER_PREFIX) :]
            user: User | None = await self._jwt_port.decode_token(token)
            if user is not None:
                logger.info(
                    LogMessage.AUTH_CREDENTIALS_VALIDATED,
                    user.sub,
                    "jwt",
                )
                return AuthContext(
                    user_id=user.sub,
                    method="jwt",
                    raw_credential=token,
                    email=user.email,
                    name=user.name,
                    username=user.username,
                )
            # Invalid JWT → no fallback to API key (matches the test contract).
            return None

        # 2. API key path — only when no Bearer token was provided.
        if api_key:
            key_hash = ApiKeyHasher.hash_key(api_key)
            found = await self._api_key_repo.find_active_by_hash(key_hash)
            if found is not None:
                user_id, key_id = found
                # Best-effort last-used tracking; never block auth on this.
                try:
                    await self._api_key_repo.touch_last_used(key_id)
                except Exception:
                    logger.debug("Failed to update last_used_at for api key %s", key_id)
                logger.info(
                    LogMessage.AUTH_CREDENTIALS_VALIDATED,
                    user_id,
                    "api_key",
                )
                return AuthContext(user_id=user_id, method="api_key", raw_credential=api_key)
            return None

        # 3. No credentials at all.
        return None
