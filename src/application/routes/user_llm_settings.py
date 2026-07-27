"""HTTP routes for per-user LLM provider settings management.

Mounted under ``/api/v1/settings/llm``. All endpoints require an authenticated
user id resolved from the request (``get_current_user_id``). The use cases are
injected via FastAPI dependencies so tests can override them.

The response is the :class:`UserLlmSettings` domain entity directly (FastAPI
serializes it automatically) — no separate Response DTO (KISS).
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.application.requests.user_llm_settings import UpsertUserLlmSettingsRequest
from src.application.use_cases.user_llm_settings.delete_user_llm_settings import DeleteUserLlmSettingsUseCase
from src.application.use_cases.user_llm_settings.get_user_llm_settings import GetUserLlmSettingsUseCase
from src.application.use_cases.user_llm_settings.upsert_user_llm_settings import UpsertUserLlmSettingsUseCase
from src.dependencies import (
    get_current_user_id,
    get_delete_user_llm_settings_use_case,
    get_get_user_llm_settings_use_case,
    get_upsert_user_llm_settings_use_case,
)
from src.domain.entities.user_llm_settings import UserLlmSettings, UserLlmSettingsInput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings/llm", tags=["llm-settings"])


@router.get("", status_code=status.HTTP_200_OK)
async def get_llm_settings(
    user_id: Annotated[str, Depends(get_current_user_id)],
    use_case: Annotated[GetUserLlmSettingsUseCase, Depends(get_get_user_llm_settings_use_case)],
) -> UserLlmSettings | None:
    """Get the authenticated user's LLM provider settings (masked API key).

    Args:
        user_id: Authenticated user id (injected).
        use_case: :class:`GetUserLlmSettingsUseCase` wired at startup.

    Returns:
        The :class:`UserLlmSettings` (masked key) or ``null`` if not configured.
    """
    return await use_case.execute(user_id)


@router.put("", status_code=status.HTTP_200_OK)
async def upsert_llm_settings(
    body: UpsertUserLlmSettingsRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    use_case: Annotated[UpsertUserLlmSettingsUseCase, Depends(get_upsert_user_llm_settings_use_case)],
) -> UserLlmSettings:
    """Insert or update the authenticated user's LLM provider settings.

    The ``api_key`` is plaintext on the wire (HTTPS) and stored encrypted at
    rest by the use case.

    Args:
        body: Request body (provider, base_url, api_key).
        user_id: Authenticated user id (injected).
        use_case: :class:`UpsertUserLlmSettingsUseCase` wired at startup.

    Returns:
        The upserted :class:`UserLlmSettings` (masked key).
    """
    return await use_case.execute(
        user_id=user_id,
        inp=UserLlmSettingsInput(**body.model_dump()),
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_settings(
    user_id: Annotated[str, Depends(get_current_user_id)],
    use_case: Annotated[DeleteUserLlmSettingsUseCase, Depends(get_delete_user_llm_settings_use_case)],
) -> None:
    """Delete the authenticated user's LLM provider settings (idempotent).

    Args:
        user_id: Authenticated user id (injected).
        use_case: :class:`DeleteUserLlmSettingsUseCase` wired at startup.
    """
    await use_case.execute(user_id)
