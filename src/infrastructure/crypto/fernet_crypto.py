"""Fernet-based symmetric encryption for per-user LLM API keys.

Wraps :class:`cryptography.fernet.Fernet` behind a small, testable facade. The
key is provided by ``Settings.secret_encryption_key`` (a URL-safe base64
Fernet key). An empty / whitespace-only key raises :class:`ValueError` at
construction so wiring fails fast in production (tests pass a fixed key).
"""

from cryptography.fernet import Fernet


class FernetCrypto:
    """Symmetric encrypt / decrypt helper for at-rest API key storage.

    Attributes:
        _fernet: The underlying :class:`Fernet` instance.
    """

    def __init__(self, key: str) -> None:
        """Initialize the Fernet cipher with a URL-safe base64 key.

        Args:
            key: A URL-safe base64 Fernet key (32 bytes encoded). Must be
                non-empty.

        Raises:
            ValueError: If ``key`` is empty or whitespace-only.
        """
        if not key or not key.strip():
            raise ValueError("FernetCrypto requires a non-empty key")
        self._fernet = Fernet(key.encode())

    def encrypt(self, plaintext: str) -> str:
        """Encrypt ``plaintext`` and return a URL-safe base64 token string.

        Args:
            plaintext: The API key plaintext.

        Returns:
            The Fernet token (str), which includes the IV + timestamp.
        """
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        """Decrypt a Fernet token and return the plaintext.

        Args:
            token: The Fernet token produced by :meth:`encrypt`.

        Returns:
            The original plaintext.

        Raises:
            cryptography.fernet.InvalidToken: If the token is tampered or was
                encrypted with a different key.
        """
        return self._fernet.decrypt(token.encode()).decode()
