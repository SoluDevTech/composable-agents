"""Use case: return the profile of the authenticated user.

Maps the :class:`~src.domain.entities.auth.auth_context.AuthContext` resolved
by the security layer to a public :class:`UserProfile` projection. Pure
mapping — no I/O, no side effects — kept as a use case so the route stays a
thin HTTP layer (Router -> Use Case).
"""

import logging

from src.domain.entities.auth.auth_context import AuthContext
from src.domain.entities.user.user_profile import UserProfile

logger = logging.getLogger(__name__)


class GetCurrentUserUseCase:
    """Build a :class:`UserProfile` from the current :class:`AuthContext`."""

    async def execute(self, ctx: AuthContext) -> UserProfile:
        """Return the public profile of the authenticated user.

        Args:
            ctx: The authentication context resolved for the current request.

        Returns:
            A :class:`UserProfile` carrying the user id and (when available)
            the email / name / username claims propagated from the JWT.
        """
        logger.info("Current user profile requested: %s", ctx.user_id)
        return UserProfile(
            user_id=ctx.user_id,
            email=ctx.email,
            name=ctx.name,
            username=ctx.username,
        )
