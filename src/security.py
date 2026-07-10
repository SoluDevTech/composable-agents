"""API key security for the Composable Agents API.

Validates the ``X-API-Key`` header against the configured master key. When the
master key is empty (dev/test), authentication is disabled with a warning.
"""

import logging
import secrets

from fastapi import Depends
from fastapi.security import APIKeyHeader

from src.domain.errors.messages import ErrorMessage
from src.domain.errors.security import InvalidApiKeyError

logger = logging.getLogger(__name__)


class ComposableAgentsSecurity:
    """Validates incoming API keys against the configured master key.

    The class is instantiated once at the composition root with the master key
    (``settings.api_key``) and its ``verify_api_key`` method is injected as a
    FastAPI dependency on protected routers. When the master key is empty the
    check is bypassed (useful for local dev/test).
    """

    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    def __init__(self, master_key: str) -> None:
        self.master_key = master_key

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
