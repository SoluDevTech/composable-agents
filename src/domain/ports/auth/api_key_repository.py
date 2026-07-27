"""Port for the API-key repository (outbound boundary).

Implemented by :class:`~src.infrastructure.postgres_api_key.adapter.PostgresApiKeyRepository`
against the ``api_keys`` table. The auth service only depends on this
abstraction, and the API-key management use cases depend on the management
methods added in this extended port.
"""

from abc import ABC, abstractmethod

from src.domain.entities.auth.api_key import ApiKeyView


class ApiKeyRepository(ABC):
    """Outbound port: persist and look up per-user API keys.

    API keys are stored hashed (SHA-256 hex of the plaintext) so lookups are
    performed on the hash, never on the plaintext. An active key is one that is
    not revoked (``revoked_at IS NULL``).
    """

    @abstractmethod
    async def find_active_by_hash(self, key_hash: str) -> tuple[str, str] | None:
        """Return ``(user_id, key_id)`` for the active key matching ``key_hash``.

        Args:
            key_hash: The SHA-256 hex digest of the API key plaintext.

        Returns:
            A ``(user_id, key_id)`` tuple if an active key matches, else ``None``.
        """
        ...

    @abstractmethod
    async def create(self, user_id: str, name: str, key_hash: str, key_prefix: str) -> str:
        """Persist a new API key and return its generated id.

        Args:
            user_id: Owner of the key.
            name: Human-readable label.
            key_hash: SHA-256 hex digest of the plaintext (never the plaintext).
            key_prefix: First 10 chars of the plaintext (for recognition).

        Returns:
            The generated key id (uuid hex).
        """
        ...

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[ApiKeyView]:
        """Return all API keys owned by ``user_id`` (active and revoked).

        Results are ordered by ``created_at`` descending (newest first). The
        hash is never included in the returned views.

        Args:
            user_id: Owner whose keys are returned.

        Returns:
            A list of :class:`ApiKeyView` (possibly empty).
        """
        ...

    @abstractmethod
    async def revoke(self, user_id: str, key_id: str) -> None:
        """Revoke the key ``key_id`` owned by ``user_id``.

        Idempotent: revoking an already-revoked key is a no-op success.

        Args:
            user_id: Owner of the key (a key owned by another user is treated
                as not found).
            key_id: Id of the key to revoke.

        Raises:
            ApiKeyNotFoundError: If no key matches ``(user_id, key_id)``.
        """
        ...

    @abstractmethod
    async def touch_last_used(self, key_id: str) -> None:
        """Update ``last_used_at`` to now for ``key_id``.

        Silent no-op if the key does not exist (used on the auth hot path where
        a stale/revoked key may still be presented).

        Args:
            key_id: Id of the key that was just used.
        """
        ...
