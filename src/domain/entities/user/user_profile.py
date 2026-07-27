"""UserProfile domain entity — public projection of the authenticated user.

Returned by the ``GET /api/v1/users/me`` endpoint. Distinct from the
:class:`~src.domain.entities.user.user.User` entity (which models the raw JWT
payload with ``extra="ignore"``) so the API contract is explicit and decoupled
from the IdP claim shape.
"""

from pydantic import BaseModel, ConfigDict


class UserProfile(BaseModel):
    """Public profile of the authenticated user.

    Attributes:
        user_id: Stable identifier (JWT ``sub`` or API-key owner id).
        email: User email (``None`` when not provided by the credential).
        name: User full name (``None`` when not provided).
        username: Username (``None`` when not provided).
    """

    model_config = ConfigDict(extra="ignore")

    user_id: str
    email: str | None = None
    name: str | None = None
    username: str | None = None
