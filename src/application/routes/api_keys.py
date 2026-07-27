"""HTTP routes for per-user API-key management.

Mounted under ``/api/v1/api-keys``. All endpoints require an authenticated
user id resolved from the request (``get_current_user_id``). The use cases are
injected via FastAPI dependencies so tests can override them.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.application.requests.api_key import CreateApiKeyRequest
from src.application.use_cases.api_key.create_api_key import CreateApiKeyUseCase
from src.application.use_cases.api_key.list_api_keys import ListApiKeysUseCase
from src.application.use_cases.api_key.revoke_api_key import RevokeApiKeyUseCase
from src.dependencies import (
    get_create_api_key_use_case,
    get_current_user_id,
    get_list_api_keys_use_case,
    get_revoke_api_key_use_case,
)
from src.domain.entities.auth.api_key import ApiKeyView, CreatedApiKey
from src.domain.logging.messages import LogMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: CreateApiKeyRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    use_case: Annotated[CreateApiKeyUseCase, Depends(get_create_api_key_use_case)],
) -> CreatedApiKey:
    """Create a new API key for the authenticated user.

    Args:
        body: Request body containing the key ``name``.
        user_id: Authenticated user id (injected).
        use_case: :class:`CreateApiKeyUseCase` wired at startup.

    Returns:
        A :class:`CreatedApiKey` carrying the plaintext (shown once).
    """
    return await use_case.execute(user_id=user_id, name=body.name)


@router.get("")
async def list_api_keys(
    user_id: Annotated[str, Depends(get_current_user_id)],
    use_case: Annotated[ListApiKeysUseCase, Depends(get_list_api_keys_use_case)],
) -> list[ApiKeyView]:
    """List all API keys owned by the authenticated user.

    Args:
        user_id: Authenticated user id (injected).
        use_case: :class:`ListApiKeysUseCase` wired at startup.

    Returns:
        A list of :class:`ApiKeyView` (no hash, no plaintext).
    """
    keys = await use_case.execute(user_id=user_id)
    logger.info(LogMessage.API_KEY_LISTED, len(keys), user_id)
    return keys


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    use_case: Annotated[RevokeApiKeyUseCase, Depends(get_revoke_api_key_use_case)],
) -> None:
    """Revoke an API key owned by the authenticated user.

    Idempotent: revoking an already-revoked key returns 204.

    Args:
        key_id: Id of the key to revoke.
        user_id: Authenticated user id (injected).
        use_case: :class:`RevokeApiKeyUseCase` wired at startup.

    Raises:
        ApiKeyNotFoundError: If the key does not exist or is owned by another
            user (HTTP 404).
    """
    logger.info(LogMessage.API_KEY_REVOKED, key_id, user_id)
    await use_case.execute(user_id=user_id, key_id=key_id)
