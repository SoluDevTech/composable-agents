"""HTTP routes for the authenticated user profile.

Mounted under ``/api/v1/users``. The ``me`` endpoint requires an authenticated
:class:`AuthContext` resolved from the request (``get_current_auth_context``)
and returns a public :class:`UserProfile` projection. The use case is injected
via a FastAPI dependency so tests can override it.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.application.use_cases.user.get_current_user import GetCurrentUserUseCase
from src.dependencies import get_current_auth_context, get_get_current_user_use_case
from src.domain.entities.auth.auth_context import AuthContext
from src.domain.entities.user.user_profile import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", status_code=status.HTTP_200_OK)
async def get_current_user(
    ctx: Annotated[AuthContext, Depends(get_current_auth_context)],
    use_case: Annotated[GetCurrentUserUseCase, Depends(get_get_current_user_use_case)],
) -> UserProfile:
    """Return the profile of the authenticated user.

    The profile claims (``email`` / ``name`` / ``username``) are propagated
    from the JWT by the auth layer; for API-key auth only ``user_id`` is
    available and the optional fields are ``null``.

    Args:
        ctx: The authentication context resolved for the current request.
        use_case: :class:`GetCurrentUserUseCase` wired at startup.

    Returns:
        A :class:`UserProfile` carrying the user id and (when available) the
        email / name / username claims.
    """
    return await use_case.execute(ctx)
